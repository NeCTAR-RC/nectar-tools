============
Installation
============

* To build some of the dependencies, you will need the python headers and their
  dependencies. You also need some extra libraries, libffi and libssl-dev.
  So to install them both, on Ubuntu::

  $ sudo apt-get install python-dev libffi-dev libssl-dev

* Install virtualenv if you do not have it installed already. You can use your
  package manager or pip. Instructions for using pip are at
  https://virtualenv.pypa.io/en/latest/installation.html
  For Ubuntu and Fedora, the package is called
  python-virtualenv. ::

  $ sudo apt-get install python-virtualenv

* Create a virtualenv and activate it::

  $ mkdir ~/env
  $ virtualenv ~/env/nectar_tools
  $ source ~/env/nectar_tools/bin/activate

* Clone this repository::

  $ sudo apt-get install git
  $ mkdir ~/src
  $ cd ~/src
  $ git clone https://github.com/NeCTAR-RC/nectar-tools.git

* Install the nectar_tools package into your virtual environment. This will
  ensure that all the necessary dependencies are also installed into this
  environment::

   $ cd nectar-tools
   $ pip install -e .
