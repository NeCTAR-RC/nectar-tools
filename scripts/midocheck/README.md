Midocheck
=========

Sanity checker for Neutron and Midonet DB.

This script checks and optionally deletes stray resources that were deleted in
Neutron but lingering in Midonet DB.

Installation
------------
Create a python3 virtualenv and install it
```
mkvirtualenv -p /usr/bin/python3 midocheck
cd midocheck
pip install .
```


Usage
------

* Check Routers
  ```
  midocheck --routers
  +--------------------------------------+---------+----------------+---------+---------+
  |                 UUID                 | Neutron | MidonetNeutron | Midonet | delete? |
  +--------------------------------------+---------+----------------+---------+---------+
  | 03c2f393-70d7-4172-b1cc-69965f814cb0 |    x    |       x        |    x    |         |
  | 1f4f06c2-b383-49de-a1a2-836687a379ce |    x    |       x        |    x    |         |
  | 50046e44-24a5-4e04-9e0d-8410c15ebf8f |    x    |       x        |    x    |         |
  | d40334ad-09e6-490e-9996-f5eee8af6e9e |    x    |       x        |    x    |         |
  +--------------------------------------+---------+----------------+---------+---------+
  ```

* Check Ports
  ```
  midocheck --ports
  ```

* Check one port
  ```
  midocheck --ports b4a99806-d541-4ad8-aa89-a435b250ec02
  +--------------------------------------+---------+----------------+---------+---------+
  |                 UUID                 | Neutron | MidonetNeutron | Midonet | delete? |
  +--------------------------------------+---------+----------------+---------+---------+
  | b4a99806-d541-4ad8-aa89-a435b250ec02 |         |       x        |    x    |    ✓    |
  +--------------------------------------+---------+----------------+---------+---------+
  ```

* Delete one port
  ```
  jake@threepio:~/work/git/self/midocheck (master *%=)$ midocheck --ports b4a99806-d541-4ad8-aa89-a435b250ec02 --delete
  +--------------------------------------+---------+----------------+---------+---------+
  |                 UUID                 | Neutron | MidonetNeutron | Midonet | delete? |
  +--------------------------------------+---------+----------------+---------+---------+
  | b4a99806-d541-4ad8-aa89-a435b250ec02 |         |       x        |    x    |    ✓    |
  +--------------------------------------+---------+----------------+---------+---------+
  Deleting resources...
  Deleting port b4a99806-d541-4ad8-aa89-a435b250ec02

  ```

NOTE: if deleting throws an error this is normally due to resources in
MidonetNeutron having their dependent resources already deleted. This error can
be ignored, or one needs to go into zookeeper to delete them
