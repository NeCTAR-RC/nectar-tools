========
Usage
========

To use NeCTAR Tools in a project::
----------------------------------

    ``import nectar_tools``

How to use the outage script
----------------------------
* If necessary, follow the instructions in `nectar-tools/docs/install.rst`.
* Source administrative credentials for the NectAR research cloud. This is to
  give the script sufficient permission to obtain the email addresses of users.
* ``cd nectar-tools/announce``
* Run the script with the -h option to get help about all the options you can
  use::

  ./outage.py -h

* If appropriate, modify the ``outage.tmpl`` and ``outage.html.tmpl`` templates
  in the templates directory.

For example, the following command (with the -y option added and an SMTP server
specified with the -p options) will mail all of the users in the 'example' zone
that there will be an outage at AEDT 0900 on the 30th June 2015 for an hour::

  ./outage.py -t -z example -st '09:00 30-06-2015' -d 1 -tz AEDT -o

*notes::*
    * No email will be sent *unless* you use the `--no-dry-run` option. You
      will also need to specify a mail server to use.
    * Currently, you can only use the test option of outage.py with the nectar
      research cloud. This is because the hardcoded test data contains tenant
      IDs from the research cloud.
