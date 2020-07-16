import argparse

from nectar_tools import cmd_base
from nectar_tools import config
from nectar_tools import notifier


CONF = config.CONFIG


# Dirty hack
class FakeResource(object):

    def __init__(self):
        self.id = None


class SendFDOutboundCmd(cmd_base.CmdBase):

    def add_args(self):
        """Handle command-line options"""
        super().add_args()
        self.parser.description = 'Send a FreshDesk outbound email'

        self.parser.add_argument('email', help='Email of recipient')
        self.parser.add_argument('-s', '--subject', help='Email subject',
                                 required=True)
        self.parser.add_argument('-b', '--body-file', required=True,
                                 type=argparse.FileType(),
                                 help='File location of body')

    def send(self):
        subject = self.args.subject
        group_id = CONF.freshdesk.provisioning_group
        body = self.args.body_file.read()
        fd = notifier.FreshDeskNotifier(None, FakeResource(), None,
                                        group_id, subject,
                                        dry_run=self.args.no_dry_run)
        fd._create_ticket(self.args.email, [], body)


def main():
    cmd = SendFDOutboundCmd()
    cmd.send()


if __name__ == '__main__':
    main()
