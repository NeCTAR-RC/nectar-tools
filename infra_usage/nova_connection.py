from util_report import process_config as get_variable
from novaclient.v1_1 import client
from novaclient.exceptions import ClientException, BadRequest

username = get_variable('production', 'user')
key = get_variable('production', 'passwd')
tenant_name = get_variable('production', 'name')
url = get_variable('production', 'url')
zone = get_variable('config', 'zone')


def create_connection():
    try:
        conn = client.Client(username=username, api_key=key,
                             project_id=tenant_name, auth_url=url)
        return conn
    except ClientException:
            return False