#!/usr/bin/python


"""
This program is a simple template driven mass emailer.

A sample query to generate a list of the user of the cloud.

SELECT rcuser.email, rcuser.displayname FROM rcshibboleth.user AS rcuser LEFT JOIN keystone.user AS kuser ON rcuser.user_id = kuser.id WHERE kuser.enabled = 1 GROUP BY rcuser.user_id INTO OUTFILE '/tmp/contacts.csv' FIELDS TERMINATED BY ',' ENCLOSED BY '"' LINES TERMINATED BY '\n';
"""
from email.MIMEText import MIMEMultipart, MIMEText
import argparse
import csv
import os
import sys
import smtplib

import jinja2

DEBUG = 0

TEMPLATE_DIR = os.path.abspath(os.path.dirname(__file__)+'/templates')
templateLoader = jinja2.FileSystemLoader(searchpath=TEMPLATE_DIR)
templateEnv = jinja2.Environment(loader=templateLoader)

global smtp_server


def collect_args():

    parser = argparse.ArgumentParser(description='Email Announcements.')

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
    parser.add_argument('-p', '--smtp_server',
                        default='127.0.0.1',)
    parser.add_argument('-v', '--verbose', action='count', default=0)

    return parser


def send_email(recipient, subject, text, html=None, print_only=False):

    global smtp_server

    msg = MIMEMultipart('alternative')
    msg.attach(MIMEText(text, 'plain', 'utf-8'))
    if html is not None:
        msg.attach(MIMEText(html, 'html', 'utf-8'))

    msg['From'] = 'NeCTAR Research Cloud <bounces@rc.nectar.org.au>'
    msg['To'] = recipient
    msg['Reply-to'] = 'support@rc.nectar.org.au'
    msg['Subject'] = subject

    if print_only:
        print '\n\n\n\n\n', msg
        return
    else:
        print 'Sending email to:', recipient

    s = smtplib.SMTP(smtp_server)
    s.set_debuglevel(DEBUG)

    try:
        s.sendmail(msg['From'], [recipient], msg.as_string())
    except smtplib.SMTPRecipientsRefused as err:
        sys.stderr.write('%s\n' % str(err))
    finally:
        s.quit()


if __name__ == "__main__":

    global smtp_server

    args = collect_args().parse_args()

    smtp_server = args.smtp_server

    template = templateEnv.get_template(args.template)

    sent_addresses = set()
    with open(args.users) as csvfile:
        for user in csv.DictReader(csvfile, fieldnames=['email', 'name']):
            if user['email'] in sent_addresses:
                print "Skipping duplicate:", user['email']
                continue
            sent_addresses.add(user['email'])
            to_address = user['email'] if not args.test else args.test_email
            content = template.render(user)
            send_email(to_address, args.subject, content,
                       print_only=args.test_template)
