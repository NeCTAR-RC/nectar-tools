from dash import Dash, dash_table, dcc, html
from dash.dependencies import Input, Output
import plotly.express as px

import pandas as pd

from cloudkittyclient import client as ck_client
from gnocchiclient import client as gclient
from plotly.subplots import make_subplots

from keystoneauth1 import loading
from keystoneauth1 import session
from keystoneclient.v3 import client as kclient
import plotly.graph_objs as go

import os
import datetime
import json

import dash_bootstrap_components as dbc

app = Dash(external_stylesheets=[dbc.themes.BOOTSTRAP])

today = datetime.date.today()
end = today.strftime("%Y-%m-%d")
begin = (today - datetime.timedelta(90)).strftime("%Y-%m-%d")

def get_session():
    username = os.environ.get('OS_USERNAME')
    password = os.environ.get('OS_PASSWORD')
    project_name = os.environ.get('OS_PROJECT_NAME')
    auth_url = os.environ.get('OS_AUTH_URL')

    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url=auth_url,
                                    username=username,
                                    password=password,
                                    project_name=project_name,
                                    user_domain_id='default',
                                    project_domain_id='default')

    return session.Session(auth=auth)

def get_cloudkitty_client(sess=None, endpoint=None):
    if not sess:
        sess = get_session()
    return ck_client.Client('2', session=sess, endpoint=endpoint)

def get_gnocchi_client(sess=None):
    if not sess:
        sess = get_session()
    return gclient.Client('1', session=sess)

def get_keystone_client(sess=None):
    if not sess:
        sess = get_session()
    return kclient.Client(session=sess)

import functools
import time

def timer(func):
    """Print the runtime of the decorated function"""
    @functools.wraps(func)
    def wrapper_timer(*args, **kwargs):
        start_time = time.perf_counter()    # 1
        value = func(*args, **kwargs)
        end_time = time.perf_counter()      # 2
        run_time = end_time - start_time    # 3
        print(f"Finished {func.__name__!r} in {run_time:.4f} secs")
        return value
    return wrapper_timer

def get_project_id():
    k_session = get_session()
    k_client = get_keystone_client(k_session)
    project_name = os.environ.get('OS_PROJECT_NAME')
    try:
        project_id=k_client.projects.get(project_name).id
    except Exception:
        project_id=os.environ.get('OS_PROJECT_ID')
    print(project_id)
    return project_id

@timer
def query_data(start_date=begin, end_date=end, groupby=['id','time-1d']):
    kwargs = {}
    project_id = get_project_id()
    kwargs['filters'] = { 'type': 'instance', 'project_id': project_id }
    kwargs['limit'] = 30000
    kwargs['begin'] = start_date
    kwargs['end'] = end_date

    k_session = get_session()
    client = get_cloudkitty_client(k_session)

    df = []
    for gb in groupby:
        kwargs['groupby'] = [gb]
        summary = client.summary.get_summary(**kwargs)
        df.append(pd.DataFrame(summary['results'], columns=summary['columns']))
    return df

@timer
def query_resources(begin=None, end=None):
    k_session = get_session()
    g_client = get_gnocchi_client(k_session)
    project_id = get_project_id()
    query = "project_id='%s'" % project_id
    if begin:
        query = query + " and ( ended_at = None or ended_at >= '%s' )" % begin
    if end:
        query = query + " and started_at <= '%s'" % end
    resources = g_client.resource.search(resource_type='instance', query=query)
    return resources

@timer
def query_dataframes(id, start_date, end_date, limit=100, offset=0):
    kwargs = {}
    kwargs['filters'] = { 'type': 'instance',
                          'id': id }
    kwargs['limit'] = limit
    kwargs['begin'] = start_date
    kwargs['end'] = end_date
    kwargs['offset'] = offset

    k_session = get_session()
    client = get_cloudkitty_client(k_session)

    columns = ['begin', 'end', 'metric', 'unit', 'qty', 'price',
        'id', 'project_id', 'user_id', 'flavor_name', 'flavor_id']
    values = []
    response = client.dataframes.get_dataframes(**kwargs)
    dataframes = response.get('dataframes', [])

    for df in dataframes:
        period = df['period']
        usage = df['usage']
        for metric_type, points in usage.items():
            for point in points:
                values.append([
                    period['begin'],
                    period['end'],
                    metric_type,
                    point['vol']['unit'],
                    point['vol']['qty'],
                    point['rating']['price'],
                    point['groupby']['id'],
                    point['groupby']['project_id'],
                    point['groupby']['user_id'],
                    point['metadata']['flavor_name'],
                    point['metadata']['flavor_id'],
                ])


    df = pd.DataFrame(values, columns=columns)
    return df

PAGE_SIZE = 100

@app.callback(
    Output('output-table', 'data'),
    Output('output-figure','figure'),
    Output('output-date-picker-range', 'children'),
    [Input('my-date-picker-range', 'start_date'),
     Input('my-date-picker-range', 'end_date')])
def update_output(start_date, end_date):
    text = 'Start is "{}" and end is "{}"'.format(start_date, end_date)
    global df_day
    global df_id
    [df_id, df_day] = query_data(start_date, end_date)
    # TODO: could be empty
    figure = make_subplots(
        rows=1, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        specs=[[{"type": "scatter"}]]
    )

    figure.add_trace(
        go.Scatter(
            x=df_day["begin"],
            y=df_day["rate"],
            mode="lines",
            name="Usage in the past 3 months"
        ),
        row=1, col=1
    )
    #df_id['flavor'] = df_id['id'].apply(query_resources)
    resources = query_resources(start_date, end_date)
    def find_flavor_from_resources(id, resources):
        if isinstance(resources, list):
            for resource in resources:
                if resource['id'] == id:
                    return resource['flavor_name']
        if resources['id'] == id:
            return resources['flavor_name']
    df_id['flavor'] = df_id['id'].apply(find_flavor_from_resources, args=(resources,))

    data = df_id.to_dict('records')
    return data, figure, text

@app.callback(
    Output('instance-table','data'),
    Output('instance-text', 'children'),
    [Input('output-table', 'active_cell'),
     Input('my-date-picker-range', 'start_date'),
     Input('my-date-picker-range', 'end_date'),
     Input('instance-table', 'page_current'),
     Input('instance-table', 'page_size')])
def update_graphs(active_cell,start_date, end_date, page_current, page_size):
    if active_cell:
        id = active_cell['row_id']
        offset = page_current * page_size
        df_df = query_dataframes(id, start_date, end_date, page_size, offset)
        data = df_df.dropna().to_dict('records')
        return data, 'Instance selected is "{}"'.format(id)
    else:
        return None, 0

app.layout = html.Div([
    dcc.DatePickerRange(
        id='my-date-picker-range',
        start_date_placeholder_text="Start Period",
        end_date_placeholder_text="End Period",
        calendar_orientation='vertical',
        clearable=True,
        with_portal=True,
        start_date=begin,
        end_date=end
    ),
    dbc.Alert(id="output-date-picker-range"),
    dbc.Alert(id='instance-text'),
    dcc.Graph(id='output-figure'),
    dash_table.DataTable(
        id='output-table',
        columns=[
            {"name": i, "id": i} for i in ['id','flavor','qty', 'rate']
            #{"name": i, "id": i} for i in ['id','qty', 'rate']
        ],
        page_current=0,
        page_size=PAGE_SIZE,
        page_action='custom',
        style_data={
            'color': 'black',
            'backgroundColor': 'white'
        },
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': 'rgb(220, 220, 220)',
            }
        ],
        style_header={
            'color': 'black',
            'fontWeight': 'bold'
        },

        filter_action='custom',
        filter_query=''
    ),
    dash_table.DataTable(
        id='instance-table',
        columns=[
            {"name": i, "id": i} for i in ['begin','id','user_id','flavor_name','qty', 'price']
        ],
        page_current=0,
        page_size=PAGE_SIZE,
        page_action='custom',
        style_data={
            'color': 'black',
            'backgroundColor': 'white'
        },
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': 'rgb(220, 220, 220)',
            }
        ],
        style_header={
            'backgroundColor': 'rgb(210, 210, 210)',
            'color': 'black',
            'fontWeight': 'bold'
        },

        filter_action='custom',
        filter_query=''
    ),
])

if __name__ == '__main__':
    app.run_server(debug=True)
