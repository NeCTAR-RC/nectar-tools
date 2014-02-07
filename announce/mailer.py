#!/usr/bin/python


"""
This program is a simple template driven mass emailer.

A sample query to generate a list of the user of the cloud.

SELECT rcuser.email, rcuser.displayname FROM rcshibboleth.user AS rcuser LEFT JOIN keystone.user AS kuser ON rcuser.user_id = kuser.id WHERE k.enabled = 1 GROUP BY rcuser.user_id INTO OUTFILE '/tmp/contacts.csv' FIELDS TERMINATED BY ',' ENCLOSED BY '"' LINES TERMINATED BY '\n';
"""
from email.MIMEText import MIMEText
import argparse
import csv
import os
import os.path
import smtplib

import jinja2

DEBUG = 0
FROM_ADDRESS = "NeCTAR RC Announce <rc-rt-bounces@melbourne.nectar.org.au>"
REPLY_TO = "support@rc.nectar.org.au"

TEXT_SUBTYPE = 'plain'

parser = argparse.ArgumentParser(
    description='Email Announcements.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument('--test', action='store_true', default=False,
                    help='send all emails to the test email account.')
parser.add_argument('--test-template', action='store_true', default=False,
                    help='print the emails but don\'t send them')
parser.add_argument('--test-email', nargs='?',
                    default=os.environ.get("MAIL", ""),
                    help='The email address to send to by default.')
parser.add_argument('--users', nargs='?',
                    required=True,
                    help='A CSV file with a list of the users.')
parser.add_argument('--template', nargs='?',
                    required=True,
                    help='The template to send to the user.')
parser.add_argument('--subject', nargs='?',
                    required=True,
                    help='The subject of the email.')
parser.add_argument('-v', '--verbose', action='count', default=0)

TEMPLATE_DIR = os.path.abspath(os.path.dirname(__file__))
templateLoader = jinja2.FileSystemLoader(searchpath=TEMPLATE_DIR)
templateEnv = jinja2.Environment(loader=templateLoader)


def mailer(from_address, to_address, email, print_only=False):
    if print_only:
        print '\n\n\n\n\n', email
    else:
        print "Sent to:", to_address
        s.sendmail(FROM_ADDRESS, to_address, email)

if __name__ == "__main__":
    args = parser.parse_args()

    template = templateEnv.get_template(args.template)
    s = smtplib.SMTP()
    s.set_debuglevel(DEBUG)
    s.connect('ns-q.melbourne.nectar.org.au')
    sent_addresses = set()
    with open(args.users) as csvfile:
        for user in csv.DictReader(csvfile, fieldnames=['email', 'name']):
            if user['email'] in sent_addresses:
                print "Skipping duplicate:", user['email']
                continue
            sent_addresses.add(user['email'])
            to_address = user['email'] if not args.test else args.test_email
            content = template.render(user)
            msg = MIMEText(content.encode('utf-8'), TEXT_SUBTYPE)
            msg['Subject'] = args.subject
            msg['Reply-To'] = REPLY_TO
            msg['From'] = FROM_ADDRESS
            mailer(FROM_ADDRESS, to_address, msg.as_string(),
                   args.test_template)
    s.close()
