import os
import datetime
import jinja2
import csv
import smtplib
import textwrap
import prettytable
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from ConfigParser import SafeConfigParser


try:
    working_path = os.getcwd()
    config_file = os.path.join(working_path, "report.ini")
    with open(config_file):
        parser = SafeConfigParser()
        parser.read(config_file)
except IOError:
    print "Error!, Config File Not Found"
    raise SystemExit


def processConfig(section, option):
    for section_name in parser.sections():
        try:
            if section_name == section:
                list_items = parser.get(section_name, option)
        except:
            list_items = None
            return list_items

    return list_items


def getOrdinal(num):
    ldig = num % 10
    l2dig = (num // 10) % 10

    if (l2dig == 1) or (ldig > 3) or (num == 20) or (num == 30):
        return '%d%s' % (num, 'th')
    else:
        return '%d%s' % (num, {1: 'st', 2: 'nd', 3: 'rd'}.get(ldig))


def getDate(type_):
    now = datetime.datetime.now()

    if type_ == 'ordinal':
        return getOrdinal(int(now.strftime("%d")))
    elif type_ == 'ordinal_date':
        return getOrdinal(int(now.strftime("%d"))) + " " + now.strftime(
                                                            "%b, %Y, %H:%M")
    elif type_ is 'std':
        return now.strftime("%d_%m_%Y_%H_%M")


def templateLoader(data_1, data_2=None, cell=None, opt=None):
    report_date = getDate('ordinal_date')
    working_path = os.getcwd()
    templateLoader = jinja2.FileSystemLoader(searchpath=working_path)
    templateEnv = jinja2.Environment(loader=templateLoader)

    file_dir = processConfig('dir', 'output_dir')
    if cell == None:
        file_name = file_dir + 'rcuall' + getDate('std') + ".html"
        TEMPLATE_FILE = "report_all_template.html"
        template = templateEnv.get_template(TEMPLATE_FILE)
        templateVars = {'title': 'NeCTAR RC Usage Report',
                    "description": "Report Gen", 'date': report_date,
                    'cell': data_1, 'rc': data_2}

    else:
        file_name = file_dir + cell + getDate('std') + ".html"
        TEMPLATE_FILE = "report_template.html"
        template = templateEnv.get_template(TEMPLATE_FILE)
        templateVars = {'title': 'NeCTAR RC Cell Usage',
                    "description": "Report Gen", 'date': report_date,
                    'cell': data_1}

    outputText = template.render(templateVars)
    with open(file_name, "wb") as fh:
        fh.write(outputText)
    if opt == 'email':
        return file_name


def createCSVFileNode(data_w):
    now = datetime.datetime.now()
    csvdir = processConfig('dir', 'output_dir')
    filename_node = csvdir + data_w.get('node_name') + ".csv"

    date_write = now.strftime("%d%m%Y%H%M")

    if os.path.exists(filename_node) is False:
        try:
            record = open(filename_node, 'w+')
            writer = csv.writer(record, delimiter=',',
                                quoting=csv.QUOTE_ALL)
            writer.writerow(['date', 'node', 'total_nodes',
                            'total_cores', 'total_mem', 'used_cores',
                            'used_mem', 'free_cores', 'free_mem',
                            'ts', 'tm', 'tl', 'txl', 'txxl', 'others'])

            writer.writerow([date_write, data_w.get('node_name'),
                             data_w.get('node_count'),
                             data_w.get('total_cores'),
                             data_w.get('total_memory'),
                             data_w.get('used_cores'),
                             data_w.get('used_memory'),
                             data_w.get('free_cores'),
                             data_w.get('free_memory'),
                             data_w.get('t_s'), data_w.get('t_m'),
                             data_w.get('t_l'), data_w.get('t_xl'),
                             data_w.get('t_xxl'), data_w.get('oth')])
        except IOError, e:
            print "File Error" % e
            raise SystemExit
    else:
        with open(filename_node, 'a') as w:
            writer = csv.writer(w, delimiter=',',
                                    quoting=csv.QUOTE_ALL)

            writer.writerow([date_write, data_w.get('node_name'),
                             data_w.get('node_count'),
                             data_w.get('total_cores'),
                             data_w.get('total_memory'),
                             data_w.get('used_cores'),
                             data_w.get('used_memory'),
                             data_w.get('free_cores'),
                             data_w.get('free_memory'),
                             data_w.get('t_s'), data_w.get('t_m'),
                             data_w.get('t_l'), data_w.get('t_xl'),
                             data_w.get('t_xxl'), data_w.get('oth')])


def multiCSVNode(data_w):
    for i in data_w:
        createCSVFileNode(i)

def createCSVFileCloud(data_w,):
    now = datetime.datetime.now()
    csvdir = processConfig('dir', 'output_dir')
    filename_all = csvdir + 'cloud_data' + ".csv"
    date_write = now.strftime("%d%m%Y%H%M")

    if os.path.exists(filename_all) is False:

            try:
                record = open(filename_all, 'w+')
                writer = csv.writer(record, delimiter=',',
                                    quoting=csv.QUOTE_ALL)
                writer.writerow(['date', 'total_nodes', 'total_cores',
                                 'total_mem', 'used_cores', 'used_mem',
                                 'free_cores', 'free_mem', 'ts', 'tm',
                                 'tl', 'txl', 'txxl', 'others'])

                writer.writerow([date_write, data_w.get('total_nodes'),
                                     data_w.get('total_cores'),
                                     data_w.get('total_mem'),
                                     data_w.get('used_cores'),
                                     data_w.get('used_mem'),
                                     data_w.get('free_cores'),
                                     data_w.get('free_mem'),
                                     data_w.get('total_small'),
                                     data_w.get('total_medium'),
                                     data_w.get('total_large'),
                                     data_w.get('total_xl'),
                                     data_w.get('total_xxl'),
                                     data_w.get('oth')]
                                        )
            except IOError, e:
                print "File Error" % e
                raise SystemExit
    else:
        with open(filename_all, 'a') as w:
            writer = csv.writer(w, delimiter=',',
                                    quoting=csv.QUOTE_ALL)

            writer.writerow([date_write, data_w.get('total_nodes'),
                            data_w.get('total_cores'), data_w.get('total_mem'),
                            data_w.get('used_cores'), data_w.get('used_mem'),
                            data_w.get('free_cores'),
                            data_w.get('free_mem'),
                            data_w.get('total_small'),
                            data_w.get('total_medium'),
                            data_w.get('total_large'),
                            data_w.get('total_xl'),
                            data_w.get('total_xxl'),
                            data_w.get('oth')])


def emailUser(email_file):

    smtp_server = processConfig('email_server', 'server')
    smtp_port = processConfig('email_server', 'port')
    fromaddr = processConfig('email_server', 'from')
    rec_user = processConfig('email_user', 'emailaddr')

    msg = MIMEMultipart()

    server = smtplib.SMTP(smtp_server, smtp_port)
    rec_user = rec_user.split(',')

    sub = 'NeCTAR Infrastructure Resource usage'

    msg['From'] = fromaddr
    msg['To'] = ",".join(rec_user)
    msg['Subject'] = sub
    f = open(email_file, 'r')
    html_data = [i for i in f]
    body = "".join(html_data)

    '''
    if os.path.exists(attach):
            part = MIMEBase('application', "octet-stream")
            part.set_payload(open(attach, "rb").read())
            Encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment; filename="%s"'
                                                % os.path.basename(attach))
            msg.attach(part)
            msg.attach(MIMEText(body, 'html'))
            text = msg.as_string()
            server.sendmail(fromaddr, rec_user, text)
            server.quit()
        else:
    '''
    msg.attach(MIMEText(body, 'html'))
    text = msg.as_string()
    server.sendmail(fromaddr, rec_user, text)
    server.quit()


def printPretty(data, dict_property="Property", wrap=0):
    pt = prettytable.PrettyTable([dict_property, 'Value'], caching=False)
    pt.align = 'l'
    for k, v in sorted(data.iteritems()):
        if isinstance(v, dict):
            v = str(v)
        if wrap > 0:
            v = textwrap.fill(str(v), wrap)
        if v and isinstance(v, basestring) and r'\n' in v:
            lines = v.strip().split(r'\n')
            col1 = k
            for line in lines:
                pt.add_row([col1, line])
                col1 = ''
        else:
            pt.add_row([k, v])
    print pt.get_string()


def printPretty2(data, wrap=0):

    pt = prettytable.PrettyTable(['Property', 'Value'], caching=False)
    pt.align = 'l'
    pt.max_width['Property'] = 30
    pt.max_width['Value'] = 40
    pt.add_row(['Node Name:', data.get('node_name')])
    pt.add_row(['Total Nodes:', data.get('node_count')])
    pt.add_row(['Total Cores:', data.get('total_cores')])
    pt.add_row(['Total Memory:', data.get('total_memory')])
    pt.add_row(['Used Cores:', data.get('used_cores')])
    pt.add_row(['Used Memory:', data.get('used_memory')])
    pt.add_row(['Free Cores:', data.get('free_cores')])
    pt.add_row(['Free Memory:', data.get('free_memory')])
    text_print = 'VM size used: (s,m,l,xl,xxl,others)'

    text_print = textwrap.fill(text_print, wrap)
    pt.add_row([text_print,
               [data.get('t_s'), data.get('t_m'), data.get('t_l'),
                data.get('t_xl'), data.get('t_xxl'), data.get('oth')]
                ])
    print pt.get_string()


def printPretty3(data, wrap=0):
    pt = prettytable.PrettyTable(['Property', 'Value'], caching=False)
    pt.align = 'l'
    pt.add_row(['Total available nodes:', data.get('total_nodes')])
    pt.add_row(['Used cores and memory:', [data.get('used_cores'),
                                          data.get('used_mem')]])
    pt.add_row(['Free cores and memory:', [data.get('free_cores'),
                                           data.get('free_mem')]])
    text_print = 'VM size used: (s,m,l,xl,xxl,others)'
    text_print = textwrap.fill(text_print, wrap)
    pt.add_row([text_print,
                [data.get('total_small'), data.get('total_medium'),
                 data.get('total_large'), data.get('total_xl'),
                 data.get('total_xxl'), data.get('oth')]
                ])
    print pt.get_string()
