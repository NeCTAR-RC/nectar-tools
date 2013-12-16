from keystoneclient.v2_0 import client
from keystoneclient.exceptions import ClientException


def createConnection(username, key, tenant_id, auth_url):
    try:
        conn = client.Client(username=username,
                             password=key,
                             tenant_name=tenant_id,
                             auth_url=auth_url)
        return conn
    except ClientException:
        return False
