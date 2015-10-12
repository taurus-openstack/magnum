# SUR 2015/08/20
# Senlin replacing Heat in Magnum
# cluster_function for bay_conductor 

import argparse
import logging
import time

from magnum.common.clients import OpenStackClients as OSC
from magnum.sur.action.senlin.clusters import Cluster
from magnum.sur.action.senlin.nodes import Node
from magnum.sur.action.senlin.profiles import Profile
from magnum.sur.action.senlin.policies import ScalingInPolicy as SIPolicy
from magnum.sur.action.senlin.policies import ScalingOutPolicy as SOPolicy
from magnum.sur.action.senlin.webhooks import Webhook

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def wait_for_node_active(sc, node):
    while True:
        status = Node.node_show(sc, node)['node']['status']
        if status == 'ACTIVE':
            break
        time.sleep(1)

def attach_policy(sc, **params):
    cluster_name = params.get('cluster_name', 'sur_cluster')

    # create scaling policy
    si_policy_name = cluster_name + '_si_policy'
    so_policy_name = cluster_name + '_so_policy'

    si_policy_spec = params.get('si_policy_spec', None)
    so_policy_spec = params.get('so_policy_spec', None)

    SIPolicy.policy_create(sc, si_policy_name, si_policy_spec)
    SOPolicy.policy_create(sc, so_policy_name, so_policy_spec)
    time.sleep(1)

    Cluster.cluster_policy_attach(sc, cluster_name, si_policy_name)
    Cluster.cluster_policy_attach(sc, cluster_name, so_policy_name)

def create_cluster(OSC, **params):
    #LOG.info('Creating Request accepted.')
    master_profile_name = params.get('master_profile_name', 'master_profile')
    minion_profile_name = params.get('minion_profile_name', 'minion_profile')

    master_profile_spec = params.get('master_profile_spec', None)
    minion_profile_spec = params.get('minion_profile_spec', None)

    cluster_name = params.get('cluster_name', 'sur_cluster')

    master_node_name = cluster_name + '_master'
    minion_node_name = cluster_name + '_minion_'
    webhook_name = cluster_name + '_so_webhook'

    node_count = params.get('node_count', 1)

    # Client
    sc = OSC.senlin()
    hc = OSC.heat()

    # Create Master Profile
    Profile.profile_create(sc, master_profile_name, 'os.heat.stack',
                           master_profile_spec, '1111')
    time.sleep(1)

    # Create Master Node
    Node.node_create(sc, master_node_name, None, master_profile_name)
    time.sleep(5)

    # Wait for Node Active
    wait_for_node_active(sc, master_node_name)

    # Get Info from Heat Stack
    master_stack_id = Node.node_show(sc, master_name)['node']['physical_id']
    HeatInfo = hc.stacks.get(master_stack_id)['outputs']
    for p in HeatInfo:
        if p['output_key'] == 'kube_master_internal':
            kube_master_internal = p['output_value']
        if p['output_key'] == 'fixed_network_id':
            fixed_network_id = p['output_value']
        if p['output_key'] == 'fixed_subnet_id':
            fixed_subnet_id = p['output_value']

    # Define Minion Yaml

    # Create Minion Profile
    Profile.profile_craete(sc, minion_profile_name, 'os.heat.stack',
                           minion_profile_spec, '1111')
    time.sleep(1)
    
    # Create Cluster
    Cluster.cluster_create(sc, cluster_name, minion_profile_name)
    time.sleep(1)

    # Master join into Cluster
    Node.node_join(sc, master_node_name, cluster_name)
    time.sleep(1)

    # Create Minion Node(s)
    for i in range(node_count):
        Node.node_create(sc, minion_node_name + str(i), cluster_name,
            minion_profile_name)
        time.sleep(5)

    # Attach Scaling Policy
    attach_policy(sc, **params)

    # Create Scale-out Webhook
    wb = Webhook.cluster_webhook_create(sc, webhook_name, cluster_name, 
                                        'CLUSTER_SCALE_OUT', {})
    time.sleep(1)
    wb_url = wb['webhook']['url']
    LOG.info('webhook_url=%s' % wb_url)

    #LOG.info('Complete') 
