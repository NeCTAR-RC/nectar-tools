import copy
import operator

from keystoneauth1 import loading as ks_loading
from oslo_config import cfg
from oslo_log import log as logging
import pbr.version


CONF = cfg.CONF

DEFAULT_CONFIG_FILE = '/etc/nectar/tools.ini'
SERVICE_AUTH_GROUP = 'service_auth'


freshdesk_opts = [
    cfg.StrOpt('domain', help='Freshdesk domain'),
    cfg.StrOpt('key', secret=True, help='Freshdesk API key'),
    cfg.IntOpt('email_config_id', help='Freshdesk email config ID'),
    cfg.IntOpt('allocation_group', help='Freshdesk allocation group ID'),
    cfg.IntOpt('pt_group', help='Freshdesk project trial group ID'),
    cfg.IntOpt('image_group', help='Freshdesk image group ID'),
    cfg.IntOpt('accounts_group', help='Freshdesk accounts group ID'),
    cfg.IntOpt('jupyterhub_group', help='Freshdesk jupyterhub group ID'),
    cfg.IntOpt('provisioning_group', help='Freshdesk provisioning group ID'),
]

keystone_opts = [
    cfg.StrOpt('member_role_id', help='ID of the member role'),
    cfg.StrOpt('manager_role_id', help='ID of the manager role'),
]

designate_opts = [
    cfg.StrOpt('user_domain', help='Domain of users to create zones for'),
    cfg.StrOpt('zone_email', help='Email address set on created zones'),
]

events_opts = [
    cfg.ListOpt(
        'notifier_queues',
        default=[],
        help='Message queues to send event notifications to',
    ),
]

image_expiry_opts = [
    cfg.ListOpt(
        'official_project_ids',
        default=[],
        help='Projects whose images are excluded from expiry',
    ),
]

limits_opts = [
    cfg.StrOpt('region_id', help='Region to set limits in'),
]

jupyterhub_opts = [
    cfg.StrOpt('api_url', help='JupyterHub API URL'),
    cfg.StrOpt('token', secret=True, help='JupyterHub API token'),
]

kubernetes_opts = [
    cfg.StrOpt('host', help='Kubernetes API host'),
    cfg.StrOpt('token', secret=True, help='Kubernetes API token'),
    cfg.StrOpt('namespace', help='Kubernetes namespace'),
]

trove_opts = [
    cfg.StrOpt('project_id', help='Trove service project ID'),
]

octavia_opts = [
    cfg.StrOpt('project_id', help='Octavia service project ID'),
]

tempest_opts = [
    cfg.ListOpt(
        'tempest_project_ids',
        default=[],
        help='Projects used by tempest test runs',
    ),
]

sentry_opts = [
    cfg.StrOpt(
        'dsn',
        secret=True,
        help='GlitchTip/Sentry compatible DSN. When set, unhandled '
        'exceptions and ERROR level log messages are reported.',
    ),
    cfg.StrOpt(
        'environment',
        help='Environment name reported with each event, '
        'e.g. production or testing.',
    ),
]

_OPTS = [
    ('freshdesk', freshdesk_opts),
    ('keystone', keystone_opts),
    ('designate', designate_opts),
    ('events', events_opts),
    ('image_expiry', image_expiry_opts),
    ('limits', limits_opts),
    ('jupyterhub', jupyterhub_opts),
    ('kubernetes_client', kubernetes_opts),
    ('trove', trove_opts),
    ('octavia', octavia_opts),
    ('tempest', tempest_opts),
    ('sentry', sentry_opts),
]

for _group, _opts in _OPTS:
    CONF.register_opts(_opts, group=_group)

logging.register_options(CONF)

ks_loading.register_auth_conf_options(CONF, SERVICE_AUTH_GROUP)
ks_loading.register_session_conf_options(CONF, SERVICE_AUTH_GROUP)


def init(args=None, **kwargs):
    version = pbr.version.VersionInfo('nectar_tools').release_string()
    CONF(
        args or [],
        project='nectar-tools',
        version=f'%prog {version}',
        **kwargs,
    )


def setup_logging(conf):
    """Sets up the logging options.

    :param conf: a cfg.ConfOpts object
    """
    logging.set_defaults(default_log_levels=logging.get_default_log_levels())
    logging.setup(conf, 'nectar-tools')


# Used by oslo-config-generator entry point
# https://docs.openstack.org/oslo.config/latest/cli/generator.html
def list_opts():
    return [*_OPTS, add_auth_opts()]


def add_auth_opts():
    opts = ks_loading.register_session_conf_options(CONF, SERVICE_AUTH_GROUP)
    opt_list = copy.deepcopy(opts)
    opt_list.insert(0, ks_loading.get_auth_common_conf_options()[0])
    for plugin_option in ks_loading.get_auth_plugin_conf_options('password'):
        if all(option.name != plugin_option.name for option in opt_list):
            opt_list.append(plugin_option)
    opt_list.sort(key=operator.attrgetter('name'))
    return (SERVICE_AUTH_GROUP, opt_list)
