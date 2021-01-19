#!/usr/bin/env python

import argparse
import datetime
from dateutil.relativedelta import relativedelta
import logging

from nectar_tools import auth
from nectar_tools import cmd_base
from nectar_tools import config

from nectar_tools.expiry.manager import account as expirer


CONFIG = config.CONFIG
LOG = logging.getLogger(__name__)


class AccountExpiryCmd(cmd_base.CmdBase):
    def __init__(self):
        super().__init__(log_filename='account-expiry.log')

        self.m_client = auth.get_manuka_client(self.session)

        accounts = []
        if self.args.account_id:
            account = self.m_client.users.get(self.args.account_id)
            accounts.append(account)
        elif self.args.all or self.args.filename:
            now = datetime.datetime.now()
            six_months_ago = now - relativedelta(months=6)
            accounts = self.m_client.users.list(last_login__lt=six_months_ago,
                                                expiry_status='active')

            if self.args.filename:
                wanted_accounts = self.read_file(self.args.filename)
                accounts = [i for i in accounts if i.id in wanted_accounts]

        else:
            LOG.error("Need to provide account id or use option --all")
        self.accounts = accounts

    def get_expirer(self, account):
        return expirer.AccountExpirer(account=account,
                                      ks_session=self.session,
                                      dry_run=self.dry_run)

    def add_args(self):
        super(AccountExpiryCmd, self).add_args()
        self.parser.description = 'Expires Nectar Accounts'
        account_group = self.parser.add_mutually_exclusive_group()
        account_group.add_argument('-f', '--filename',
                                 type=argparse.FileType('r'),
                                 help='File path with a list of account IDs, \
                                 one on each line')
        account_group.add_argument('-i', '--account-id',
                                 help='Account ID to process')
        account_group.add_argument('--all', action='store_true',
                                 help='Run over all accounts')
        self.parser.add_argument('-l', '--limit',
                                 type=int,
                                 default=0,
                                 help='Only process this many \
                                 eligible accounts')
        self.parser.add_argument('-o', '--offset',
                                 type=int,
                                 default=None,
                                 help='Skip this many accounts \
                                 before processing')

    def process_accounts(self):
        LOG.info("Processing accounts")

        limit = self.args.limit
        offset = self.args.offset
        offset_count = 0
        processed = 0

        for account in self.accounts:
            offset_count += 1
            if offset is None or offset_count > offset:
                try:
                    LOG.debug("------------------")
                    ex = self.get_expirer(account)
                    if ex.process():
                        processed += 1
                except Exception:
                    LOG.exception('Exception processing Account %s',
                                  account.id)
                    processed += 1

            if limit > 0 and processed >= limit:
                break
        LOG.info("Processed %s accounts", processed)
        return processed


def main():
    cmd = AccountExpiryCmd()
    cmd.process_accounts()


if __name__ == '__main__':
    main()
