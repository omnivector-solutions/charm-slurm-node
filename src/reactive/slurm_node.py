from os import chmod
from socket import gethostname

from charms.slurm.helpers import MUNGE_SERVICE
from charms.slurm.helpers import MUNGE_KEY_PATH
from charms.slurm.helpers import SLURMD_SERVICE
from charms.slurm.helpers import SLURM_CONFIG_PATH
from charms.slurm.helpers import SLURMCTLD_SERVICE
from charms.slurm.helpers import create_spool_dir
from charms.slurm.helpers import render_munge_key
from charms.slurm.helpers import render_slurm_config

from charmhelpers.core.host import service_stop
from charmhelpers.core.host import service_pause
from charmhelpers.core.host import service_start
from charmhelpers.core.host import service_restart
from charmhelpers.core.host import service_running
from charmhelpers.core.hookenv import config
from charmhelpers.core.hookenv import status_set
from charmhelpers.core.hookenv import storage_get

import charms.reactive as reactive
import charms.reactive.flags as flags


flags.register_trigger(when='slurm-cluster.active.changed',
                       clear_flag='slurm-node.configured')


@reactive.only_once()
@reactive.when('slurm.installed')
def initial_setup():
    status_set('maintenance', 'Initial setup of slurm-node')
    # Disable slurmctld on node
    service_pause(SLURMCTLD_SERVICE)


@reactive.when_not('endpoint.slurm-cluster.joined')
def missing_controller():
    status_set('blocked', 'Missing a relation to slurm-controller')
    # Stop slurmd
    service_stop(SLURMD_SERVICE)
    flags.clear_flag('slurm-node.configured')
    flags.clear_flag('slurm-node.info.sent')


@reactive.when('endpoint.slurm-cluster.joined')
@reactive.when_not('slurm-node.info.sent')
def send_node_info(cluster_endpoint):
    cluster_endpoint.send_node_info(hostname=gethostname(),
                                    partition=config('partition'),
                                    default=config('default'))
    flags.set_flag('slurm-node.info.sent')


#@reactive.when('endpoint.slurm-cluster.joined')
@reactive.when('endpoint.slurm-cluster.active.changed')
@reactive.when_not('slurm-node.configured')
def configure_node(cluster_endpoint):
    status_set('maintenance', 'Configuring slurm-node')

    controller_data = cluster_endpoint.active_data
    create_spool_dir(context=controller_data)
    render_munge_key(context=controller_data)
    render_slurm_config(context=controller_data)
    # Make sure slurmd is running
    if not service_running(SLURMD_SERVICE):
        service_start(SLURMD_SERVICE)

    flags.set_flag('slurm-node.configured')
    flags.clear_flag('endpoint.slurm-cluster.active.changed')


@reactive.when('endpoint.slurm-cluster.joined', 'slurm-node.configured')
def node_ready(cluster_endpoint):
    status_set('active', 'Ready')


@reactive.hook('config-changed')
def config_changed():
    flags.clear_flag('slurm-node.configured')
    flags.clear_flag('slurm-node.info.sent')


@reactive.hook('scratch-storage-attached')
def setup_storage():
    storage = storage_get()
    chmod(path=storage.get('location'), mode=0o777)


@reactive.when_file_changed(SLURM_CONFIG_PATH)
def restart_on_slurm_change():
    service_restart(SLURMD_SERVICE)


@reactive.when_file_changed(MUNGE_KEY_PATH)
def restart_on_munge_change():
    service_restart(MUNGE_SERVICE)
