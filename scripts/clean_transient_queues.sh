#!/bin/bash


VHOST=blue; for i in `rabbitmqadmin -V $VHOST list queues -d 3 name consumers messages  | grep '| 0         | 0' | grep engine | awk '{print $2}'`; do echo "deleting $i"; rabbitmqadmin -V $VHOST delete queue name=$i; done
VHOST=green; for i in `rabbitmqadmin -V $VHOST list queues -d 3 name consumers messages  | grep '| 0         | 0' | grep engine | awk '{print $2}'`; do echo "deleting $i"; rabbitmqadmin -V $VHOST delete queue name=$i; done
VHOST=nectar; for i in `rabbitmqadmin -V $VHOST list queues -d 3 name consumers messages  | grep '| 0         | 0' | grep central | awk '{print $2}'`; do echo "deleting $i"; rabbitmqadmin -V $VHOST delete queue name=$i; done
VHOST=nectar; for i in `rabbitmqadmin -V $VHOST list queues -d 3 name consumers messages  | grep '| 0         | 0' | grep magnum-cond | awk '{print $2}'`; do echo "deleting $i"; rabbitmqadmin -V $VHOST delete queue name=$i; done
VHOST=nectar; for i in `rabbitmqadmin -V $VHOST list queues -d 3 name consumers messages  | grep '| 0         | 0' | grep results | awk '{print $2}'`; do echo "deleting $i"; rabbitmqadmin -V $VHOST delete queue name=$i; done
VHOST=nectar; for i in `rabbitmqadmin -V $VHOST list queues -d 3 name consumers messages  | grep '| 0         | 0' | grep tasks | awk '{print $2}'`; do echo "deleting $i"; rabbitmqadmin -V $VHOST delete queue name=$i; done



VHOST=nectar; for i in `rabbitmqadmin -V $VHOST list queues -d 3 name consumers messages  | grep '| 0         | 0' | grep 'q-' | awk '{print $2}'`; do echo "deleting $i"; rabbitmqadmin -V $VHOST delete queue name=$i; done
VHOST=nectar; for i in `rabbitmqadmin -V $VHOST list queues -d 3 name consumers messages  | grep '| 0         | 0' | grep neutron | awk '{print $2}'`; do echo "deleting $i"; rabbitmqadmin -V $VHOST delete queue name=$i; done
VHOST=nectar; for i in `rabbitmqadmin -V $VHOST list queues -d 3 name consumers messages  | grep '| 0         | 0' | grep worker | awk '{print $2}'`; do echo "deleting $i"; rabbitmqadmin -V $VHOST delete queue name=$i; done
VHOST=nectar; for i in `rabbitmqadmin -V $VHOST list queues -d 3 name consumers messages  | grep '| 0         | 0' | grep cinder | awk '{print $2}'`; do echo "deleting $i"; rabbitmqadmin -V $VHOST delete queue name=$i; done
VHOST=nectar; for i in `rabbitmqadmin -V $VHOST list queues -d 3 name consumers messages  | grep '| 0         | 0' | grep dhcp_agent | awk '{print $2}'`; do echo "deleting $i"; rabbitmqadmin -V $VHOST delete queue name=$i; done
