import copy
import json
import logging
import multiprocessing
import unittest
from datetime import timedelta, datetime
from multiprocessing import Process
from unittest import mock
from unittest.mock import call

import pika
import pika.exceptions
from freezegun import freeze_time
from parameterized import parameterized

from src.message_broker.rabbitmq import RabbitMQApi
from src.monitors.managers.network import NetworkMonitorsManager
from src.monitors.starters import (
    start_cosmos_network_monitor, start_substrate_network_monitor)
from src.utils import env
from src.utils.constants.names import (
    COSMOS_NETWORK_MONITOR_NAME_TEMPLATE,
    SUBSTRATE_NETWORK_MONITOR_NAME_TEMPLATE)
from src.utils.constants.rabbitmq import (
    HEALTH_CHECK_EXCHANGE, CONFIG_EXCHANGE,
    NETWORK_MON_MAN_HEARTBEAT_QUEUE_NAME, NETWORK_MON_MAN_CONFIGS_QUEUE_NAME,
    MONITORABLE_EXCHANGE, HEARTBEAT_OUTPUT_MANAGER_ROUTING_KEY,
    PING_ROUTING_KEY, NODES_CONFIGS_ROUTING_KEY_CHAINS)
from src.utils.exceptions import PANICException, MessageWasNotDeliveredException
from test.test_utils.utils import (
    infinite_fn, connect_to_rabbit, delete_queue_if_exists,
    delete_exchange_if_exists, disconnect_from_rabbit)
from test.utils.cosmos.cosmos import CosmosTestNodes
from test.utils.substrate.substrate import SubstrateTestNodes


class TestNetworkMonitorsManager(unittest.TestCase):
    def setUp(self) -> None:
        # Some dummy data
        self.dummy_logger = logging.getLogger('Dummy')
        self.dummy_logger.disabled = True
        self.connection_check_time_interval = timedelta(seconds=0)
        self.rabbit_ip = env.RABBIT_IP
        self.rabbitmq = RabbitMQApi(
            self.dummy_logger, self.rabbit_ip,
            connection_check_time_interval=self.connection_check_time_interval)
        self.manager_name = 'test_network_monitors_manager'
        self.test_queue_name = 'Test Queue'
        self.test_data_str_1 = 'test data 1'
        self.test_data_str_2 = 'test data 2'
        self.test_data_str_3 = 'test data 3'
        self.test_heartbeat = {
            'component_name': 'Test Component',
            'is_alive': True,
            'timestamp': datetime(2012, 1, 1).timestamp(),
        }
        self.test_exception = PANICException('test_exception', 1)

        # Some dummy processes
        self.dummy_process1 = Process(target=infinite_fn, args=())
        self.dummy_process1.daemon = True
        self.dummy_process2 = Process(target=infinite_fn, args=())
        self.dummy_process2.daemon = True
        self.dummy_process3 = Process(target=infinite_fn, args=())
        self.dummy_process3.daemon = True

        # Some configuration examples
        self.cosmos_test_nodes = CosmosTestNodes()
        self.substrate_test_nodes = SubstrateTestNodes()
        self.chain_1 = 'cosmos cosmoshub'
        self.base_chain_1 = 'cosmos'
        self.sub_chain_1 = 'cosmoshub'
        self.chain_2 = 'substrate polkadot'
        self.base_chain_2 = 'substrate'
        self.sub_chain_2 = 'polkadot'
        self.chain_3 = 'cosmos akash'
        self.base_chain_3 = 'cosmos'
        self.sub_chain_3 = 'akash'
        self.parent_id_1 = 'test_parent_id_1'
        self.parent_id_2 = 'test_parent_id_2'
        self.parent_id_3 = 'test_parent_id_3'
        self.cosmos_test_nodes.archive_validator.set_parent_id(self.parent_id_1)
        self.cosmos_test_nodes.archive_non_validator.set_parent_id(
            self.parent_id_1)
        self.substrate_test_nodes.archive_validator.set_parent_id(
            self.parent_id_2)
        self.substrate_test_nodes.archive_non_validator.set_parent_id(
            self.parent_id_2)
        self.substrate_test_nodes.pruned_validator.set_parent_id(
            self.parent_id_2)
        self.substrate_test_nodes.pruned_non_validator.set_parent_id(
            self.parent_id_2)
        self.cosmos_test_nodes.pruned_validator.set_parent_id(self.parent_id_3)
        self.cosmos_test_nodes.pruned_non_validator.set_parent_id(
            self.parent_id_3)
        self.data_sources_1 = [self.cosmos_test_nodes.archive_non_validator,
                               self.cosmos_test_nodes.archive_validator]
        self.data_sources_2 = [self.substrate_test_nodes.archive_non_validator,
                               self.substrate_test_nodes.archive_validator]
        self.data_sources_3 = [self.cosmos_test_nodes.pruned_non_validator,
                               self.cosmos_test_nodes.pruned_validator]
        self.governance_addresses_1 = ['gov_addr_1', 'gov_addr_2', 'gov_addr_3']

        # Some config_process_dict, network_configs, and sent_configs examples.
        # Here we will assume that only configurations 1 and 2 are in the state.
        self.config_process_dict_example = {
            self.chain_1: {
                'component_name':
                    COSMOS_NETWORK_MONITOR_NAME_TEMPLATE.format(
                        self.sub_chain_1),
                'process': self.dummy_process1,
                'data_sources': self.data_sources_1,
                'parent_id': self.parent_id_1,
                'base_chain': self.base_chain_1,
                'sub_chain': self.sub_chain_1,
                'starter_fn': start_cosmos_network_monitor,
                'network_monitor_name_template':
                    COSMOS_NETWORK_MONITOR_NAME_TEMPLATE,
                'args': ()
            },
            self.chain_2: {
                'component_name':
                    SUBSTRATE_NETWORK_MONITOR_NAME_TEMPLATE.format(
                        self.sub_chain_2),
                'process': self.dummy_process2,
                'data_sources': self.data_sources_2,
                'parent_id': self.parent_id_2,
                'base_chain': self.base_chain_2,
                'sub_chain': self.sub_chain_2,
                'starter_fn': start_substrate_network_monitor,
                'network_monitor_name_template':
                    SUBSTRATE_NETWORK_MONITOR_NAME_TEMPLATE,
                'args': (self.governance_addresses_1,)
            }
        }
        self.network_configs_example = {
            self.chain_1: {
                'parent_id': self.parent_id_1,
                'data_sources': self.data_sources_1,
                'monitor_network': True
            },
            self.chain_2: {
                'parent_id': self.parent_id_2,
                'data_sources': self.data_sources_2,
                'monitor_network': True,
                'governance_addresses': self.governance_addresses_1
            },
        }
        self.sent_configs_example_cosmos_hub = {
            self.cosmos_test_nodes.archive_validator.node_id: {
                'id': self.cosmos_test_nodes.archive_validator.node_id,
                'parent_id': self.parent_id_1,
                'name': self.cosmos_test_nodes.archive_validator.node_name,
                'monitor_node': str(
                    self.cosmos_test_nodes.archive_validator.monitor_node
                ),
                'cosmos_rest_url':
                    self.cosmos_test_nodes.archive_validator.cosmos_rest_url,
                'monitor_cosmos_rest': str(
                    self.cosmos_test_nodes.archive_validator.monitor_cosmos_rest
                ),
                'prometheus_url':
                    self.cosmos_test_nodes.archive_validator.prometheus_url,
                'monitor_prometheus': str(
                    self.cosmos_test_nodes.archive_validator.monitor_prometheus
                ),
                'exporter_url': '',
                'monitor_system': 'True',
                'is_validator': str(
                    self.cosmos_test_nodes.archive_validator.is_validator
                ),
                'is_archive_node': str(
                    self.cosmos_test_nodes.archive_validator.is_archive_node
                ),
                'use_as_data_source': str(
                    self.cosmos_test_nodes.archive_validator.use_as_data_source
                ),
                'monitor_network': 'True',
                'operator_address':
                    self.cosmos_test_nodes.archive_validator.operator_address,
                'cometbft_rpc_url':
                    self.cosmos_test_nodes.archive_validator.cometbft_rpc_url,
                'monitor_cometbft_rpc': str(
                    (self.cosmos_test_nodes.archive_validator
                     .monitor_cometbft_rpc)
                )
            },
            self.cosmos_test_nodes.archive_non_validator.node_id: {
                'id': self.cosmos_test_nodes.archive_non_validator.node_id,
                'parent_id': self.parent_id_1,
                'name': self.cosmos_test_nodes.archive_non_validator.node_name,
                'monitor_node': str(
                    self.cosmos_test_nodes.archive_non_validator.monitor_node
                ),
                'cosmos_rest_url':
                    self.cosmos_test_nodes.archive_non_validator
                        .cosmos_rest_url,
                'monitor_cosmos_rest': str(
                    (self.cosmos_test_nodes.archive_non_validator
                     .monitor_cosmos_rest)
                ),
                'prometheus_url':
                    self.cosmos_test_nodes.archive_non_validator.prometheus_url,
                'monitor_prometheus': str(
                    (self.cosmos_test_nodes.archive_non_validator
                     .monitor_prometheus)
                ),
                'exporter_url': '',
                'monitor_system': 'True',
                'is_validator': str(
                    self.cosmos_test_nodes.archive_non_validator.is_validator
                ),
                'is_archive_node': str(
                    self.cosmos_test_nodes.archive_non_validator.is_archive_node
                ),
                'use_as_data_source': str(
                    (self.cosmos_test_nodes.archive_non_validator
                     .use_as_data_source)
                ),
                'monitor_network': 'True',
                'operator_address':
                    (self.cosmos_test_nodes.archive_non_validator
                     .operator_address),
                'cometbft_rpc_url':
                    (self.cosmos_test_nodes.archive_non_validator
                     .cometbft_rpc_url),
                'monitor_cometbft_rpc': str(
                    (self.cosmos_test_nodes.archive_non_validator
                     .monitor_cometbft_rpc)
                )
            }
        }
        self.sent_configs_example_polkadot = {
            self.substrate_test_nodes.archive_validator.node_id: {
                'id': self.substrate_test_nodes.archive_validator.node_id,
                'parent_id': self.parent_id_2,
                'name': self.substrate_test_nodes.archive_validator.node_name,
                'monitor_node': str(
                    self.substrate_test_nodes.archive_validator.monitor_node
                ),
                'node_ws_url':
                    self.substrate_test_nodes.archive_validator.node_ws_url,
                'exporter_url': '',
                'monitor_system': 'True',
                'stash_address':
                    self.substrate_test_nodes.archive_validator.stash_address,
                'is_validator': str(
                    self.substrate_test_nodes.archive_validator.is_validator),
                'is_archive_node': str(
                    self.substrate_test_nodes.archive_validator.is_archive_node
                ),
                'use_as_data_source': 'True',
                'governance_addresses': ','.join(self.governance_addresses_1),
                'monitor_network': 'True',
            },
            self.substrate_test_nodes.archive_non_validator.node_id: {
                'id': self.substrate_test_nodes.archive_non_validator.node_id,
                'parent_id': self.parent_id_2,
                'name':
                    self.substrate_test_nodes.archive_non_validator.node_name,
                'monitor_node': str(
                    self.substrate_test_nodes.archive_non_validator.monitor_node
                ),
                'node_ws_url':
                    self.substrate_test_nodes.archive_non_validator.node_ws_url,
                'exporter_url': '',
                'monitor_system': 'True',
                'stash_address':
                    self.substrate_test_nodes.archive_non_validator.
                        stash_address,
                'is_validator': str(
                    self.substrate_test_nodes.archive_non_validator.is_validator
                ),
                'is_archive_node': str(
                    self.substrate_test_nodes.archive_non_validator
                        .is_archive_node),
                'use_as_data_source': 'True',
                'governance_addresses': ','.join(self.governance_addresses_1),
                'monitor_network': 'True',
            },
        }

        # The following config will generate errors when the fields are
        # extracted
        self.sent_configs_example_cosmos_hub_errors = {
            self.cosmos_test_nodes.archive_validator.node_id: {
                'id': self.cosmos_test_nodes.archive_validator.node_id,
                'parent_id': self.parent_id_1,
                'name': self.cosmos_test_nodes.archive_validator.node_name,
                'monitor_node': str(
                    self.cosmos_test_nodes.archive_validator.monitor_node
                ),
                'cosmos_rest_url':
                    self.cosmos_test_nodes.archive_validator.cosmos_rest_url,
                'monitor_cosmos_rest': str(
                    self.cosmos_test_nodes.archive_validator.monitor_cosmos_rest
                ),
                'prometheus_url':
                    self.cosmos_test_nodes.archive_validator.prometheus_url,
                'monitor_prometheus': str(
                    self.cosmos_test_nodes.archive_validator.monitor_prometheus
                ),
                'exporter_url': '',
                'monitor_system': 'True',
                'is_validator': str(
                    self.cosmos_test_nodes.archive_validator.is_validator
                ),
                'is_archive_node': str(
                    self.cosmos_test_nodes.archive_validator.is_archive_node
                ),
                'use_as_data_source': 'False',
                'monitor_network': 'True',
                'operator_address':
                    self.cosmos_test_nodes.archive_validator.operator_address,
                'cometbft_rpc_url':
                    self.cosmos_test_nodes.archive_validator.cometbft_rpc_url,
                'monitor_cometbft_rpc': str(
                    (self.cosmos_test_nodes.archive_validator
                     .monitor_cometbft_rpc)
                )
            },
            self.cosmos_test_nodes.archive_non_validator.node_id: {
                'id': self.cosmos_test_nodes.archive_non_validator.node_id,
                'parent_id': self.parent_id_2,
                'name': self.cosmos_test_nodes.archive_non_validator.node_name,
                'monitor_node': str(
                    self.cosmos_test_nodes.archive_non_validator.monitor_node
                ),
                'cosmos_rest_url': str(
                    self.cosmos_test_nodes.archive_non_validator.cosmos_rest_url
                ),
                'monitor_cosmos_rest': str(
                    (self.cosmos_test_nodes.archive_non_validator
                     .monitor_cosmos_rest)
                ),
                'prometheus_url':
                    self.cosmos_test_nodes.archive_non_validator.prometheus_url,
                'monitor_prometheus': str(
                    (self.cosmos_test_nodes.archive_non_validator
                     .monitor_prometheus)
                ),
                'exporter_url': '',
                'monitor_system': 'True',
                'is_validator': str(
                    self.cosmos_test_nodes.archive_non_validator.is_validator
                ),
                'is_archive_node': str(
                    self.cosmos_test_nodes.archive_non_validator.is_archive_node
                ),
                'use_as_data_source': 'False',
                'monitor_network': 'False',
                'operator_address':
                    (self.cosmos_test_nodes.archive_non_validator
                     .operator_address),
                'cometbft_rpc_url':
                    (self.cosmos_test_nodes.archive_non_validator
                     .cometbft_rpc_url),
                'monitor_cometbft_rpc': str(
                    (self.cosmos_test_nodes.archive_non_validator
                     .monitor_cometbft_rpc)
                )
            }
        }
        self.sent_configs_example_polkadot_errors = {
            self.substrate_test_nodes.archive_validator.node_id: {
                'id': self.substrate_test_nodes.archive_validator.node_id,
                'parent_id': self.parent_id_3,
                'name': self.substrate_test_nodes.archive_validator.node_name,
                'monitor_node': str(
                    self.substrate_test_nodes.archive_validator.monitor_node
                ),
                'node_ws_url':
                    self.substrate_test_nodes.archive_validator.node_ws_url,
                'exporter_url': '',
                'monitor_system': 'True',
                'stash_address':
                    self.substrate_test_nodes.archive_validator.stash_address,
                'is_validator': str(
                    self.substrate_test_nodes.archive_validator.is_validator),
                'is_archive_node': str(
                    self.substrate_test_nodes.archive_validator.is_archive_node
                ),
                'use_as_data_source': 'False',
                'governance_addresses': 'bad_gov_addr',
                'monitor_network': 'False',
            },
            self.substrate_test_nodes.archive_non_validator.node_id: {
                'id': self.substrate_test_nodes.archive_non_validator.node_id,
                'parent_id': self.parent_id_2,
                'name':
                    self.substrate_test_nodes.archive_non_validator.node_name,
                'monitor_node': str(
                    self.substrate_test_nodes.archive_non_validator.monitor_node
                ),
                'node_ws_url':
                    self.substrate_test_nodes.archive_non_validator.node_ws_url,
                'exporter_url': '',
                'monitor_system': 'True',
                'stash_address':
                    self.substrate_test_nodes.archive_non_validator.
                        stash_address,
                'is_validator': str(
                    self.substrate_test_nodes.archive_non_validator.is_validator
                ),
                'is_archive_node': str(
                    self.substrate_test_nodes.archive_non_validator
                        .is_archive_node),
                'use_as_data_source': 'False',
                'governance_addresses': ','.join(self.governance_addresses_1),
                'monitor_network': 'True',
            },
        }

        # Test manager instance
        self.test_manager = NetworkMonitorsManager(
            self.dummy_logger, self.manager_name, self.rabbitmq)

        # Relevant routing keys
        self.routing_key_cosmoshub = 'chains.cosmos.cosmoshub.nodes_config'
        self.routing_key_polkadot = 'chains.substrate.polkadot.nodes_config'

    def tearDown(self) -> None:
        # Delete any queues and exchanges which are common across many tests
        connect_to_rabbit(self.test_manager.rabbitmq)
        delete_queue_if_exists(self.test_manager.rabbitmq, self.test_queue_name)
        delete_queue_if_exists(self.test_manager.rabbitmq,
                               NETWORK_MON_MAN_HEARTBEAT_QUEUE_NAME)
        delete_queue_if_exists(self.test_manager.rabbitmq,
                               NETWORK_MON_MAN_CONFIGS_QUEUE_NAME)
        delete_exchange_if_exists(self.test_manager.rabbitmq,
                                  HEALTH_CHECK_EXCHANGE)
        delete_exchange_if_exists(self.test_manager.rabbitmq, CONFIG_EXCHANGE)
        delete_exchange_if_exists(self.test_manager.rabbitmq,
                                  MONITORABLE_EXCHANGE)
        disconnect_from_rabbit(self.test_manager.rabbitmq)

        self.dummy_logger = None
        self.rabbitmq = None
        self.connection_check_time_interval = None
        self.dummy_process1 = None
        self.dummy_process2 = None
        self.dummy_process3 = None
        self.test_exception = None
        self.config_process_dict_example = None
        self.network_configs_example = None
        self.sent_configs_example_cosmos_hub = None
        self.sent_configs_example_cosmos_hub_errors = None
        self.test_manager = None
        self.cosmos_test_nodes.clear_attributes()
        self.cosmos_test_nodes = None
        self.substrate_test_nodes.clear_attributes()
        self.substrate_test_nodes = None

    def test_str_returns_manager_name(self) -> None:
        self.assertEqual(self.manager_name, str(self.test_manager))

    def test_config_process_dict_returns_config_process_dict(self) -> None:
        self.test_manager._config_process_dict = \
            self.config_process_dict_example
        self.assertEqual(self.config_process_dict_example,
                         self.test_manager.config_process_dict)

    def test_name_returns_manager_name(self) -> None:
        self.assertEqual(self.manager_name, self.test_manager.name)

    def test_network_configs_returns_network_configs(self) -> None:
        self.test_manager._network_configs = self.network_configs_example
        self.assertEqual(self.network_configs_example,
                         self.test_manager.network_configs)

    @mock.patch.object(RabbitMQApi, "start_consuming")
    def test_listen_for_data_calls_start_consuming(
            self, mock_start_consuming) -> None:
        mock_start_consuming.return_value = None
        self.test_manager._listen_for_data()
        mock_start_consuming.assert_called_once()

    def test_send_heartbeat_sends_a_heartbeat_correctly(self) -> None:
        # This test creates a queue which receives messages with the same
        # routing key as the ones sent by send_heartbeat, and checks that the
        # heartbeat is received
        self.test_manager._initialise_rabbitmq()

        # Delete the queue before to avoid messages in the queue on error.
        self.test_manager.rabbitmq.queue_delete(self.test_queue_name)

        res = self.test_manager.rabbitmq.queue_declare(
            queue=self.test_queue_name, durable=True, exclusive=False,
            auto_delete=False, passive=False
        )
        self.assertEqual(0, res.method.message_count)
        self.test_manager.rabbitmq.queue_bind(
            queue=self.test_queue_name, exchange=HEALTH_CHECK_EXCHANGE,
            routing_key=HEARTBEAT_OUTPUT_MANAGER_ROUTING_KEY)
        self.test_manager._send_heartbeat(self.test_heartbeat)

        # By re-declaring the queue again we can get the number of messages
        # in the queue.
        res = self.test_manager.rabbitmq.queue_declare(
            queue=self.test_queue_name, durable=True, exclusive=False,
            auto_delete=False, passive=True
        )
        self.assertEqual(1, res.method.message_count)

        # Check that the message received is actually the HB
        _, _, body = self.test_manager.rabbitmq.basic_get(self.test_queue_name)
        self.assertEqual(self.test_heartbeat, json.loads(body))

    @mock.patch.object(RabbitMQApi, 'basic_consume')
    def test_initialise_rabbitmq_initialises_everything_as_expected(
            self, mock_basic_consume) -> None:
        mock_basic_consume.return_value = None

        # To make sure that there is no connection/channel already established
        self.assertIsNone(self.rabbitmq.connection)
        self.assertIsNone(self.rabbitmq.channel)

        # To make sure that the exchanges and queues have not already been
        # declared
        self.rabbitmq.connect()
        self.test_manager.rabbitmq.queue_delete(
            NETWORK_MON_MAN_HEARTBEAT_QUEUE_NAME)
        self.test_manager.rabbitmq.queue_delete(
            NETWORK_MON_MAN_CONFIGS_QUEUE_NAME)
        self.test_manager.rabbitmq.exchange_delete(HEALTH_CHECK_EXCHANGE)
        self.test_manager.rabbitmq.exchange_delete(CONFIG_EXCHANGE)
        self.test_manager.rabbitmq.exchange_delete(MONITORABLE_EXCHANGE)
        self.rabbitmq.disconnect()

        self.test_manager._initialise_rabbitmq()

        # Perform checks that the connection has been opened, marked as open
        # and that the delivery confirmation variable is set.
        self.assertTrue(self.test_manager.rabbitmq.is_connected)
        self.assertTrue(self.test_manager.rabbitmq.connection.is_open)
        self.assertTrue(
            self.test_manager.rabbitmq.channel._delivery_confirmation)

        # Check whether the exchanges and queues have been creating by
        # sending messages with the same routing keys as for the queues, and
        # checking what messages have been received if any.
        self.test_manager.rabbitmq.basic_publish_confirm(
            exchange=HEALTH_CHECK_EXCHANGE, routing_key=PING_ROUTING_KEY,
            body=self.test_data_str_1, is_body_dict=False,
            properties=pika.BasicProperties(delivery_mode=2), mandatory=True)
        self.test_manager.rabbitmq.basic_publish_confirm(
            exchange=CONFIG_EXCHANGE,
            routing_key=NODES_CONFIGS_ROUTING_KEY_CHAINS,
            body=self.test_data_str_2, is_body_dict=False,
            properties=pika.BasicProperties(delivery_mode=2), mandatory=True)

        # Re-declare queues to get the number of messages and the msgs received
        res = self.test_manager.rabbitmq.queue_declare(
            NETWORK_MON_MAN_HEARTBEAT_QUEUE_NAME, False, True, False, False)
        self.assertEqual(1, res.method.message_count)
        _, _, body = self.test_manager.rabbitmq.basic_get(
            NETWORK_MON_MAN_HEARTBEAT_QUEUE_NAME)
        self.assertEqual(self.test_data_str_1, body.decode())

        res = self.test_manager.rabbitmq.queue_declare(
            NETWORK_MON_MAN_CONFIGS_QUEUE_NAME, False, True, False, False)
        self.assertEqual(1, res.method.message_count)
        _, _, body = self.test_manager.rabbitmq.basic_get(
            NETWORK_MON_MAN_CONFIGS_QUEUE_NAME)
        self.assertEqual(self.test_data_str_2, body.decode())

        # Check that basic_consume was called twice, once for each consumer
        # queue
        calls = mock_basic_consume.call_args_list
        self.assertEqual(2, len(calls))

        # Check that the publishing exchanges were created by sending messages
        # to them. If this fails an exception is raised hence the test fails.
        self.test_manager.rabbitmq.basic_publish_confirm(
            exchange=MONITORABLE_EXCHANGE, routing_key='test_key',
            body=self.test_data_str_3, is_body_dict=False,
            properties=pika.BasicProperties(delivery_mode=2), mandatory=False)

    @parameterized.expand([
        ('self.sent_configs_example_cosmos_hub', 'self.parent_id_1',
         'self.data_sources_1', 'True',),
        ('self.sent_configs_example_cosmos_hub_errors', 'None', '[]', 'None',),
    ])
    def test_extract_network_monitoring_fields_from_cosmos_configs(
            self, sent_configs, expected_parent_id, expected_data_sources,
            expected_monitor_network) -> None:
        parent_id, data_sources, monitor_network = \
            self.test_manager \
                ._extract_network_monitoring_fields_from_cosmos_configs(
                eval(sent_configs))
        self.assertEqual(eval(expected_parent_id), parent_id)
        self.assertListEqual(eval(expected_data_sources), data_sources)
        self.assertEqual(eval(expected_monitor_network), monitor_network)

    @parameterized.expand([
        ('self.sent_configs_example_polkadot', 'self.parent_id_2',
         'self.data_sources_2', 'True', 'self.governance_addresses_1'),
        ('self.sent_configs_example_polkadot_errors', 'None', '[]', 'None',
         'None'),
    ])
    def test_extract_network_monitoring_fields_from_substrate_configs(
            self, sent_configs, expected_parent_id, expected_data_sources,
            expected_monitor_network, expected_governance_addresses) -> None:
        parent_id, data_sources, monitor_network, governance_addresses = \
            self.test_manager \
                ._extract_network_monitoring_fields_from_substrate_configs(
                eval(sent_configs))
        self.assertEqual(eval(expected_parent_id), parent_id)
        self.assertListEqual(eval(expected_data_sources), data_sources)
        self.assertEqual(eval(expected_monitor_network), monitor_network)
        self.assertEqual(eval(expected_governance_addresses),
                         governance_addresses)

    @mock.patch.object(multiprocessing.Process, "start")
    @mock.patch.object(multiprocessing, 'Process')
    def test_create_and_start_network_monitor_process_stores_correctly(
            self, mock_init, mock_start) -> None:
        mock_start.return_value = None
        mock_init.return_value = self.dummy_process3
        self.test_manager._config_process_dict = \
            self.config_process_dict_example
        expected_state = {
            self.chain_1: self.config_process_dict_example[self.chain_1],
            self.chain_2: self.config_process_dict_example[self.chain_2],
            self.chain_3: {
                'component_name':
                    COSMOS_NETWORK_MONITOR_NAME_TEMPLATE.format(
                        self.sub_chain_3),
                'process': self.dummy_process3,
                'data_sources': self.data_sources_3,
                'parent_id': self.parent_id_3,
                'base_chain': self.base_chain_3,
                'sub_chain': self.sub_chain_3,
                'starter_fn': start_cosmos_network_monitor,
                'network_monitor_name_template':
                    COSMOS_NETWORK_MONITOR_NAME_TEMPLATE,
                'args': ()
            }
        }

        self.test_manager._create_and_start_network_monitor_process(
            self.data_sources_3, self.parent_id_3, self.chain_3,
            self.base_chain_3, self.sub_chain_3, start_cosmos_network_monitor,
            COSMOS_NETWORK_MONITOR_NAME_TEMPLATE
        )

        self.assertEqual(expected_state, self.test_manager.config_process_dict)

    @mock.patch.object(multiprocessing.Process, "start")
    def test_create_and_start_network_monitor_process_creates_correctly(
            self, mock_start) -> None:
        mock_start.return_value = None

        self.test_manager._create_and_start_network_monitor_process(
            self.data_sources_3, self.parent_id_3, self.chain_3,
            self.base_chain_3, self.sub_chain_3, start_cosmos_network_monitor,
            COSMOS_NETWORK_MONITOR_NAME_TEMPLATE
        )

        new_entry = self.test_manager.config_process_dict[self.chain_3]
        new_entry_process = new_entry['process']
        self.assertTrue(new_entry_process.daemon)
        self.assertEqual(3, len(new_entry_process._args))
        self.assertEqual(self.data_sources_3, new_entry_process._args[0])
        self.assertEqual(self.parent_id_3, new_entry_process._args[1])
        self.assertEqual(self.sub_chain_3, new_entry_process._args[2])
        self.assertEqual(start_cosmos_network_monitor,
                         new_entry_process._target)

    @mock.patch.object(multiprocessing.Process, "start")
    def test_create_and_start_network_monitor_process_starts_process(
            self, mock_start) -> None:
        self.test_manager._create_and_start_network_monitor_process(
            self.data_sources_3, self.parent_id_3, self.chain_3,
            self.base_chain_3, self.sub_chain_3, start_cosmos_network_monitor,
            COSMOS_NETWORK_MONITOR_NAME_TEMPLATE,
        )
        mock_start.assert_called_once()

    @mock.patch.object(NetworkMonitorsManager,
                       "process_and_send_monitorable_data")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    def test_process_cosmos_node_configs_creates_new_monitor_if_none_running(
            self, mock_create_and_start, mock_process_send_mon_data) -> None:
        """
        In this test we will check that if a valid nodes' configuration for
        network monitoring is received and no Cosmos network monitor has
        been started for that chain, a new one is started.
        """
        mock_create_and_start.return_value = None
        mock_process_send_mon_data.return_value = None
        expected_configs = {
            'parent_id': self.parent_id_1,
            'data_sources': self.data_sources_1,
            'monitor_network': True
        }

        actual_configs = self.test_manager._process_cosmos_node_configs(
            self.sent_configs_example_cosmos_hub, {}, self.chain_1,
            self.base_chain_1, self.sub_chain_1)

        mock_create_and_start.assert_called_once_with(
            self.data_sources_1, self.parent_id_1, self.chain_1,
            self.base_chain_1, self.sub_chain_1, start_cosmos_network_monitor,
            COSMOS_NETWORK_MONITOR_NAME_TEMPLATE)
        self.assertEqual(expected_configs, actual_configs)

    @mock.patch.object(NetworkMonitorsManager,
                       "process_and_send_monitorable_data")
    @mock.patch.object(multiprocessing.Process, "terminate")
    @mock.patch.object(multiprocessing.Process, "join")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    def test_process_cosmos_node_configs_stops_and_creates_if_newer_confs(
            self, mock_create_and_start, mock_join, mock_terminate,
            mock_process_send_mon_data) -> None:
        """
        In this test we will check that if a new valid nodes' configuration for
        network monitoring is received and a Cosmos network monitor has
        already been started for that chain, the old is stopped and a new one is
        started.
        """
        mock_create_and_start.return_value = None
        mock_join.return_value = None
        mock_terminate.return_value = None
        mock_process_send_mon_data.return_value = None
        expected_configs = {
            'parent_id': self.parent_id_1,
            'data_sources': self.data_sources_1,
            'monitor_network': True
        }
        current_configs = {
            self.chain_1: {
                'parent_id': self.parent_id_1,
                'data_sources': [self.cosmos_test_nodes.archive_validator],
                'monitor_network': True
            },
        }
        self.test_manager._config_process_dict = \
            self.config_process_dict_example

        actual_configs = self.test_manager._process_cosmos_node_configs(
            self.sent_configs_example_cosmos_hub, current_configs[self.chain_1],
            self.chain_1, self.base_chain_1, self.sub_chain_1)

        mock_terminate.assert_called_once()
        mock_join.assert_called_once()
        mock_create_and_start.assert_called_once_with(
            self.data_sources_1, self.parent_id_1, self.chain_1,
            self.base_chain_1, self.sub_chain_1, start_cosmos_network_monitor,
            COSMOS_NETWORK_MONITOR_NAME_TEMPLATE)
        self.assertEqual(expected_configs, actual_configs)

    @mock.patch.object(NetworkMonitorsManager,
                       "process_and_send_monitorable_data")
    @mock.patch.object(multiprocessing.Process, "terminate")
    @mock.patch.object(multiprocessing.Process, "join")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    def test_process_cosmos_node_configs_stops_monitor_if_configs_removed(
            self, mock_create_and_start, mock_join, mock_terminate,
            mock_process_send_mon_data) -> None:
        """
        In this test we will check that if configurations for network monitoring
        have been removed for a chain and a Cosmos network monitor has
        already been started for that chain, the old is stopped. In addition to
        this we will check that the function outputs the correct network
        configuration
        """
        mock_create_and_start.return_value = None
        mock_join.return_value = None
        mock_terminate.return_value = None
        mock_process_send_mon_data.return_value = None
        current_configs = {
            self.chain_1: {
                'parent_id': self.parent_id_1,
                'data_sources': self.data_sources_1,
                'monitor_network': True
            },
        }
        self.test_manager._config_process_dict = \
            self.config_process_dict_example

        actual_configs = self.test_manager._process_cosmos_node_configs(
            {}, current_configs[self.chain_1], self.chain_1,
            self.base_chain_1, self.sub_chain_1)

        mock_terminate.assert_called_once()
        mock_join.assert_called_once()
        mock_create_and_start.assert_not_called()
        self.assertEqual({}, actual_configs)
        self.assertTrue(
            self.chain_1 not in self.test_manager.config_process_dict)

    @mock.patch.object(multiprocessing.Process, "terminate")
    @mock.patch.object(multiprocessing.Process, "join")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    def test_process_cosmos_node_configs_does_nothing_if_unchanged_confs(
            self, mock_create_and_start, mock_join, mock_terminate) -> None:
        """
        In this test we will check that if we receive unchanged configurations
        for network monitoring and a Cosmos network monitor has already been
        started for that chain, nothing is done.
        """
        mock_create_and_start.return_value = None
        mock_terminate.return_value = None
        mock_join.return_value = None
        current_configs = {
            self.chain_1: {
                'parent_id': self.parent_id_1,
                'data_sources': self.data_sources_1,
                'monitor_network': True
            },
        }
        self.test_manager._config_process_dict = \
            self.config_process_dict_example

        actual_confs = self.test_manager._process_cosmos_node_configs(
            self.sent_configs_example_cosmos_hub, current_configs[self.chain_1],
            self.chain_1, self.base_chain_1, self.sub_chain_1)

        mock_terminate.assert_not_called()
        mock_join.assert_not_called()
        mock_create_and_start.assert_not_called()
        self.assertEqual(current_configs[self.chain_1], actual_confs)
        self.assertTrue(self.chain_1 in self.test_manager.config_process_dict)

    @mock.patch.object(NetworkMonitorsManager,
                       "process_and_send_monitorable_data")
    @mock.patch.object(multiprocessing.Process, "terminate")
    @mock.patch.object(multiprocessing.Process, "join")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    def test_process_cosmos_node_configs_does_nothing_if_invalid_confs(
            self, mock_create_and_start, mock_join, mock_terminate,
            mock_process_send_mon_data) -> None:
        """
        In this test we will check that if we receive invalid configurations
        for network monitoring, nothing is done. Note here we will assume that
        no network monitor has started yet, as otherwise it is expected that the
        monitor is to be killed.
        """
        mock_create_and_start.return_value = None
        mock_join.return_value = None
        mock_terminate.return_value = None
        mock_process_send_mon_data.return_value = None

        actual_configs = self.test_manager._process_cosmos_node_configs(
            self.sent_configs_example_cosmos_hub_errors, {}, self.chain_1,
            self.base_chain_1, self.sub_chain_1)

        mock_terminate.assert_not_called()
        mock_join.assert_not_called()
        mock_create_and_start.assert_not_called()
        self.assertEqual({}, actual_configs)
        self.assertFalse(self.chain_1 in self.test_manager.config_process_dict)

    @mock.patch.object(NetworkMonitorsManager,
                       "process_and_send_monitorable_data")
    @mock.patch.object(multiprocessing.Process, "terminate")
    @mock.patch.object(multiprocessing.Process, "join")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    def test_process_cosmos_node_confs_does_nothing_if_monitor_network_false(
            self, mock_create_and_start, mock_join, mock_terminate,
            mock_process_send_mon_data) -> None:
        """
        In this test we will check that if we receive configurations with
        monitor_network=False, nothing is done. Note here we will assume that no
        network monitor has started yet, as otherwise it is expected that the
        monitor is to be killed.
        """
        mock_create_and_start.return_value = None
        mock_join.return_value = None
        mock_terminate.return_value = None
        mock_process_send_mon_data.return_value = None
        self.sent_configs_example_cosmos_hub[
            self.cosmos_test_nodes.archive_validator.node_id][
            'monitor_network'] = 'False'
        self.sent_configs_example_cosmos_hub[
            self.cosmos_test_nodes.archive_non_validator.node_id][
            'monitor_network'] = 'False'

        actual_confs = self.test_manager._process_cosmos_node_configs(
            self.sent_configs_example_cosmos_hub, {}, self.chain_1,
            self.base_chain_1, self.sub_chain_1)

        mock_terminate.assert_not_called()
        mock_join.assert_not_called()
        mock_create_and_start.assert_not_called()
        self.assertEqual({}, actual_confs)
        self.assertFalse(self.chain_1 in self.test_manager.config_process_dict)

    @mock.patch.object(NetworkMonitorsManager,
                       "process_and_send_monitorable_data")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    def test_process_substrate_node_configs_creates_new_monitor_if_none_running(
            self, mock_create_and_start, mock_process_send_mon_data) -> None:
        """
        In this test we will check that if a valid nodes' configuration for
        network monitoring is received and no Substrate network monitor has
        been started for that chain, a new one is started.
        """
        mock_create_and_start.return_value = None
        mock_process_send_mon_data.return_value = None
        expected_configs = {
            'parent_id': self.parent_id_2,
            'data_sources': self.data_sources_2,
            'monitor_network': True,
            'governance_addresses': self.governance_addresses_1
        }

        actual_configs = self.test_manager._process_substrate_node_configs(
            self.sent_configs_example_polkadot, {}, self.chain_2,
            self.base_chain_2, self.sub_chain_2)

        mock_create_and_start.assert_called_once_with(
            self.data_sources_2, self.parent_id_2, self.chain_2,
            self.base_chain_2, self.sub_chain_2,
            start_substrate_network_monitor,
            SUBSTRATE_NETWORK_MONITOR_NAME_TEMPLATE,
            self.governance_addresses_1)
        self.assertEqual(expected_configs, actual_configs)

    @mock.patch.object(NetworkMonitorsManager,
                       "process_and_send_monitorable_data")
    @mock.patch.object(multiprocessing.Process, "terminate")
    @mock.patch.object(multiprocessing.Process, "join")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    def test_process_substrate_node_configs_stops_and_creates_if_newer_confs(
            self, mock_create_and_start, mock_join, mock_terminate,
            mock_process_send_mon_data) -> None:
        """
        In this test we will check that if a new valid nodes' configuration for
        network monitoring is received and a Substrate network monitor has
        already been started for that chain, the old is stopped and a new one is
        started.
        """
        mock_create_and_start.return_value = None
        mock_join.return_value = None
        mock_terminate.return_value = None
        mock_process_send_mon_data.return_value = None
        expected_configs = {
            'parent_id': self.parent_id_2,
            'data_sources': self.data_sources_2,
            'monitor_network': True,
            'governance_addresses': self.governance_addresses_1
        }
        current_configs = {
            self.chain_2: {
                'parent_id': self.parent_id_2,
                'data_sources': [self.substrate_test_nodes.archive_validator],
                'monitor_network': True,
                'governance_addresses': self.governance_addresses_1
            },
        }
        self.test_manager._config_process_dict = \
            self.config_process_dict_example

        actual_configs = self.test_manager._process_substrate_node_configs(
            self.sent_configs_example_polkadot, current_configs[self.chain_2],
            self.chain_2, self.base_chain_2, self.sub_chain_2)

        mock_terminate.assert_called_once()
        mock_join.assert_called_once()
        mock_create_and_start.assert_called_once_with(
            self.data_sources_2, self.parent_id_2, self.chain_2,
            self.base_chain_2, self.sub_chain_2,
            start_substrate_network_monitor,
            SUBSTRATE_NETWORK_MONITOR_NAME_TEMPLATE,
            self.governance_addresses_1)
        self.assertEqual(expected_configs, actual_configs)

    @mock.patch.object(NetworkMonitorsManager,
                       "process_and_send_monitorable_data")
    @mock.patch.object(multiprocessing.Process, "terminate")
    @mock.patch.object(multiprocessing.Process, "join")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    def test_process_substrate_node_configs_stops_monitor_if_configs_removed(
            self, mock_create_and_start, mock_join, mock_terminate,
            mock_process_send_mon_data) -> None:
        """
        In this test we will check that if configurations for network monitoring
        have been removed for a chain and a Substrate network monitor has
        already been started for that chain, the old is stopped. In addition to
        this we will check that the function outputs the correct network
        configuration
        """
        mock_create_and_start.return_value = None
        mock_join.return_value = None
        mock_terminate.return_value = None
        mock_process_send_mon_data.return_value = None
        current_configs = {
            self.chain_2: {
                'parent_id': self.parent_id_2,
                'data_sources': self.data_sources_2,
                'monitor_network': True,
                'governance_addresses': self.governance_addresses_1
            },
        }
        self.test_manager._config_process_dict = \
            self.config_process_dict_example

        actual_configs = self.test_manager._process_substrate_node_configs(
            {}, current_configs[self.chain_2], self.chain_2,
            self.base_chain_2, self.sub_chain_2)

        mock_terminate.assert_called_once()
        mock_join.assert_called_once()
        mock_create_and_start.assert_not_called()
        self.assertEqual({}, actual_configs)
        self.assertTrue(
            self.chain_2 not in self.test_manager.config_process_dict)

    @mock.patch.object(multiprocessing.Process, "terminate")
    @mock.patch.object(multiprocessing.Process, "join")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    def test_process_substrate_node_configs_does_nothing_if_unchanged_confs(
            self, mock_create_and_start, mock_join, mock_terminate) -> None:
        """
        In this test we will check that if we receive unchanged configurations
        for network monitoring and a Substrate network monitor has already been
        started for that chain, nothing is done.
        """
        mock_create_and_start.return_value = None
        mock_terminate.return_value = None
        mock_join.return_value = None
        current_configs = {
            self.chain_2: {
                'parent_id': self.parent_id_2,
                'data_sources': self.data_sources_2,
                'monitor_network': True,
                'governance_addresses': self.governance_addresses_1
            },
        }
        self.test_manager._config_process_dict = \
            self.config_process_dict_example

        actual_confs = self.test_manager._process_substrate_node_configs(
            self.sent_configs_example_polkadot, current_configs[self.chain_2],
            self.chain_2, self.base_chain_2, self.sub_chain_2)

        mock_terminate.assert_not_called()
        mock_join.assert_not_called()
        mock_create_and_start.assert_not_called()
        self.assertEqual(current_configs[self.chain_2], actual_confs)
        self.assertTrue(self.chain_2 in self.test_manager.config_process_dict)

    @mock.patch.object(NetworkMonitorsManager,
                       "process_and_send_monitorable_data")
    @mock.patch.object(multiprocessing.Process, "terminate")
    @mock.patch.object(multiprocessing.Process, "join")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    def test_process_substrate_node_configs_does_nothing_if_invalid_confs(
            self, mock_create_and_start, mock_join, mock_terminate,
            mock_process_send_mon_data) -> None:
        """
        In this test we will check that if we receive invalid configurations
        for network monitoring, nothing is done. Note here we will assume that
        no network monitor has started yet, as otherwise it is expected that the
        monitor is to be killed.
        """
        mock_create_and_start.return_value = None
        mock_join.return_value = None
        mock_terminate.return_value = None
        mock_process_send_mon_data.return_value = None

        actual_configs = self.test_manager._process_substrate_node_configs(
            self.sent_configs_example_polkadot_errors, {}, self.chain_2,
            self.base_chain_2, self.sub_chain_2)

        mock_terminate.assert_not_called()
        mock_join.assert_not_called()
        mock_create_and_start.assert_not_called()
        self.assertEqual({}, actual_configs)
        self.assertFalse(self.chain_2 in self.test_manager.config_process_dict)

    @mock.patch.object(NetworkMonitorsManager,
                       "process_and_send_monitorable_data")
    @mock.patch.object(multiprocessing.Process, "terminate")
    @mock.patch.object(multiprocessing.Process, "join")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    def test_process_substrate_node_confs_does_nothing_if_monitor_network_false(
            self, mock_create_and_start, mock_join, mock_terminate,
            mock_process_send_mon_data) -> None:
        """
        In this test we will check that if we receive configurations with
        monitor_network=False, nothing is done. Note here we will assume that no
        network monitor has started yet, as otherwise it is expected that the
        monitor is to be killed.
        """
        mock_create_and_start.return_value = None
        mock_join.return_value = None
        mock_terminate.return_value = None
        mock_process_send_mon_data.return_value = None
        self.sent_configs_example_polkadot[
            self.substrate_test_nodes.archive_validator.node_id][
            'monitor_network'] = 'False'
        self.sent_configs_example_polkadot[
            self.substrate_test_nodes.archive_non_validator.node_id][
            'monitor_network'] = 'False'

        actual_confs = self.test_manager._process_substrate_node_configs(
            self.sent_configs_example_polkadot, {}, self.chain_2,
            self.base_chain_2, self.sub_chain_2)

        mock_terminate.assert_not_called()
        mock_join.assert_not_called()
        mock_create_and_start.assert_not_called()
        self.assertEqual({}, actual_confs)
        self.assertFalse(self.chain_2 in self.test_manager.config_process_dict)

    @mock.patch.object(RabbitMQApi, "basic_ack")
    @mock.patch.object(NetworkMonitorsManager, "_process_cosmos_node_configs")
    def test_process_configs_calls_process_cosmos_node_configs_correctly(
            self, mock_process_cosmos_configs, mock_basic_ack) -> None:
        """
        In this test we will check that if cosmos configs are received,
        self._process_cosmos_node_configs is called correctly irrelevant if
        there is state already stored or not
        """
        mock_process_cosmos_configs.return_value = None
        mock_basic_ack.return_value = None

        # Must create a connection so that the blocking channel is passed
        self.test_manager.rabbitmq.connect()
        blocking_channel = self.test_manager.rabbitmq.channel
        method = pika.spec.Basic.Deliver(routing_key=self.routing_key_cosmoshub)
        body = bytes(json.dumps(self.sent_configs_example_cosmos_hub), 'utf-8')
        properties = pika.spec.BasicProperties()

        # Test with no state
        self.test_manager._process_configs(blocking_channel, method, properties,
                                           body)
        mock_process_cosmos_configs.assert_called_once_with(
            self.sent_configs_example_cosmos_hub, {}, self.chain_1,
            self.base_chain_1, self.sub_chain_1)
        mock_basic_ack.assert_called_once()
        mock_process_cosmos_configs.reset_mock()
        mock_basic_ack.reset_mock()

        # Test with state already saved
        self.test_manager._network_configs = copy.deepcopy(
            self.network_configs_example)
        self.test_manager._process_configs(blocking_channel, method, properties,
                                           body)
        mock_process_cosmos_configs.assert_called_once_with(
            self.sent_configs_example_cosmos_hub,
            self.network_configs_example[self.chain_1], self.chain_1,
            self.base_chain_1, self.sub_chain_1)
        mock_basic_ack.assert_called_once()

    @mock.patch.object(RabbitMQApi, "basic_ack")
    @mock.patch.object(NetworkMonitorsManager,
                       "_process_substrate_node_configs")
    def test_process_configs_calls_process_substrate_node_configs_correctly(
            self, mock_process_substrate_configs, mock_basic_ack) -> None:
        """
        In this test we will check that if substrate configs are received,
        self._process_substrate_node_configs is called correctly irrelevant if
        there is state already stored or not
        """
        mock_process_substrate_configs.return_value = None
        mock_basic_ack.return_value = None

        # Must create a connection so that the blocking channel is passed
        self.test_manager.rabbitmq.connect()
        blocking_channel = self.test_manager.rabbitmq.channel
        method = pika.spec.Basic.Deliver(routing_key=self.routing_key_polkadot)
        body = bytes(json.dumps(self.sent_configs_example_polkadot), 'utf-8')
        properties = pika.spec.BasicProperties()

        # Test with no state
        self.test_manager._process_configs(blocking_channel, method, properties,
                                           body)
        mock_process_substrate_configs.assert_called_once_with(
            self.sent_configs_example_polkadot, {}, self.chain_2,
            self.base_chain_2, self.sub_chain_2)
        mock_basic_ack.assert_called_once()
        mock_process_substrate_configs.reset_mock()
        mock_basic_ack.reset_mock()

        # Test with state already saved
        self.test_manager._network_configs = copy.deepcopy(
            self.network_configs_example)
        self.test_manager._process_configs(blocking_channel, method, properties,
                                           body)
        mock_process_substrate_configs.assert_called_once_with(
            self.sent_configs_example_polkadot,
            self.network_configs_example[self.chain_2], self.chain_2,
            self.base_chain_2, self.sub_chain_2)
        mock_basic_ack.assert_called_once()

    @mock.patch.object(RabbitMQApi, "basic_ack")
    @mock.patch.object(NetworkMonitorsManager,
                       "_process_substrate_node_configs")
    @mock.patch.object(NetworkMonitorsManager, "_process_cosmos_node_configs")
    def test_process_configs_stores_network_configs_if_recognized_chain(
            self, mock_process_cosmos_configs, mock_process_substrate_configs,
            mock_basic_ack) -> None:
        """
        In this test we will check that if cosmos or substrate configs are
        received, they are stored correctly after processing.
        """
        mock_process_cosmos_configs.return_value = self.test_data_str_1
        mock_process_substrate_configs.return_value = self.test_data_str_2
        mock_basic_ack.return_value = None

        # Must create a connection so that the blocking channel is passed
        self.test_manager.rabbitmq.connect()
        blocking_channel = self.test_manager.rabbitmq.channel
        method_cosmos = pika.spec.Basic.Deliver(
            routing_key=self.routing_key_cosmoshub)
        method_polkadot = pika.spec.Basic.Deliver(
            routing_key=self.routing_key_polkadot)
        body_cosmos = bytes(json.dumps(self.sent_configs_example_cosmos_hub),
                            'utf-8')
        body_polkadot = bytes(json.dumps(self.sent_configs_example_polkadot),
                              'utf-8')
        properties = pika.spec.BasicProperties()

        self.test_manager._process_configs(blocking_channel, method_polkadot,
                                           properties, body_polkadot)
        self.test_manager._process_configs(blocking_channel, method_cosmos,
                                           properties, body_cosmos)
        expected_confs = {
            self.chain_1: self.test_data_str_1,
            self.chain_2: self.test_data_str_2
        }
        self.assertEqual(expected_confs, self.test_manager.network_configs)
        self.assertEqual(2, len(mock_basic_ack.call_args_list))

    @mock.patch.object(RabbitMQApi, "basic_ack")
    @mock.patch.object(NetworkMonitorsManager,
                       "_process_substrate_node_configs")
    @mock.patch.object(NetworkMonitorsManager, "_process_cosmos_node_configs")
    def test_process_confs_no_proc_and_stores_empty_dict_for_unrecognized_chain(
            self, mock_process_cosmos_configs, mock_process_substrate_configs,
            mock_basic_ack) -> None:
        """
        In this test we will check that if configs belonging to unrecognized
        chains are received, no processing is conducted and an empty dict is
        stored for that chain.
        """
        mock_process_cosmos_configs.return_value = None
        mock_process_substrate_configs.return_value = None
        mock_basic_ack.return_value = None

        # Must create a connection so that the blocking channel is passed
        self.test_manager.rabbitmq.connect()
        blocking_channel = self.test_manager.rabbitmq.channel
        method = pika.spec.Basic.Deliver(
            routing_key='chains.chainlink.bsc.nodes_config')
        body = bytes(json.dumps(self.sent_configs_example_polkadot), 'utf-8')
        properties = pika.spec.BasicProperties()

        self.test_manager._process_configs(blocking_channel, method, properties,
                                           body)
        expected_confs = {
            'chainlink bsc': {}
        }
        self.assertEqual(expected_confs, self.test_manager.network_configs)
        mock_process_cosmos_configs.assert_not_called()
        mock_process_substrate_configs.assert_not_called()
        mock_basic_ack.assert_called_once()

    @parameterized.expand([
        ([True, True], [],),
        ([True, False], ['self.chain_2'],),
        ([False, False], ['self.chain_1', 'self.chain_2'],),
    ])
    @freeze_time("2012-01-01")
    @mock.patch.object(multiprocessing.Process, "join")
    @mock.patch.object(multiprocessing.Process, "is_alive")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    @mock.patch.object(NetworkMonitorsManager, "_send_heartbeat")
    def test_process_ping_sends_a_valid_hb(
            self, is_alive_side_effect, dead_configs, mock_send_hb,
            mock_create_and_start, mock_is_alive, mock_join) -> None:
        mock_send_hb.return_value = None
        mock_join.return_value = None
        mock_create_and_start.return_value = None
        mock_is_alive.side_effect = is_alive_side_effect
        dead_configs_eval = list(map(eval, dead_configs))
        self.test_manager._config_process_dict = \
            self.config_process_dict_example

        # Some variables below are needed as parameters for the process_ping
        # function
        self.test_manager._initialise_rabbitmq()
        blocking_channel = self.test_manager.rabbitmq.channel
        method = pika.spec.Basic.Deliver(routing_key=PING_ROUTING_KEY)
        body = b'ping'
        properties = pika.spec.BasicProperties()

        self.test_manager._process_ping(blocking_channel, method, properties,
                                        body)

        expected_hb = {
            'component_name': self.manager_name,
            'running_processes': [
                self.config_process_dict_example[chain_name]['component_name']
                for chain_name in self.config_process_dict_example
                if chain_name not in dead_configs_eval
            ],
            'dead_processes': [
                self.config_process_dict_example[chain_name]['component_name']
                for chain_name in self.config_process_dict_example
                if chain_name in dead_configs_eval
            ],
            'timestamp': datetime.now().timestamp()
        }
        mock_send_hb.assert_called_once_with(expected_hb)

    @parameterized.expand([
        ([True, True], [],),
        ([True, False], ['self.chain_2'],),
        ([False, False], ['self.chain_1', 'self.chain_2'],),
    ])
    @freeze_time("2012-01-01")
    @mock.patch.object(multiprocessing.Process, "join")
    @mock.patch.object(multiprocessing.Process, "is_alive")
    @mock.patch.object(NetworkMonitorsManager,
                       "_create_and_start_network_monitor_process")
    @mock.patch.object(NetworkMonitorsManager, "_send_heartbeat")
    def test_process_ping_restarts_dead_processes_correctly(
            self, is_alive_side_effect, dead_configs, mock_send_hb,
            mock_create_and_start, mock_is_alive, mock_join) -> None:
        mock_send_hb.return_value = None
        mock_join.return_value = None
        mock_create_and_start.return_value = None
        mock_is_alive.side_effect = is_alive_side_effect
        dead_configs_eval = list(map(eval, dead_configs))
        self.test_manager._config_process_dict = \
            self.config_process_dict_example
        expected_calls = [
            call(self.config_process_dict_example[chain_name]['data_sources'],
                 self.config_process_dict_example[chain_name]['parent_id'],
                 chain_name, chain_name.split(' ')[0], chain_name.split(' ')[1],
                 self.config_process_dict_example[chain_name]['starter_fn'],
                 self.config_process_dict_example[chain_name][
                     'network_monitor_name_template'],
                 *self.config_process_dict_example[chain_name]['args']
                 )
            for chain_name in self.config_process_dict_example
            if chain_name in dead_configs_eval
        ]

        # Some variables below are needed as parameters for the process_ping
        # function
        self.test_manager._initialise_rabbitmq()
        blocking_channel = self.test_manager.rabbitmq.channel
        method = pika.spec.Basic.Deliver(routing_key=PING_ROUTING_KEY)
        body = b'ping'
        properties = pika.spec.BasicProperties()

        self.test_manager._process_ping(blocking_channel, method, properties,
                                        body)

        actual_calls = mock_create_and_start.call_args_list
        self.assertEqual(expected_calls, actual_calls)

    @mock.patch.object(multiprocessing.Process, "is_alive")
    @mock.patch.object(NetworkMonitorsManager, "_send_heartbeat")
    def test_process_ping_does_not_send_hb_if_processing_fails(
            self, mock_send_hb, mock_is_alive) -> None:
        mock_is_alive.side_effect = self.test_exception
        mock_send_hb.return_value = None
        self.test_manager._config_process_dict = \
            self.config_process_dict_example

        # Some variables below are needed as parameters for the process_ping
        # function
        self.test_manager._initialise_rabbitmq()
        blocking_channel = self.test_manager.rabbitmq.channel
        method = pika.spec.Basic.Deliver(routing_key=PING_ROUTING_KEY)
        body = b'ping'
        properties = pika.spec.BasicProperties()

        self.test_manager._process_ping(blocking_channel, method,
                                        properties, body)

        mock_send_hb.assert_not_called()

    def test_proc_ping_send_hb_does_not_raise_msg_not_del_exce_if_hb_not_routed(
            self) -> None:
        """
        In this test we are assuming that no configs have been set, this is done
        to keep the test as simple as possible. We are also assuming that a
        MsgWasNotDeliveredException will be raised automatically because we are
        deleting the HealthExchange after every test, and thus there are no
        consumers of the heartbeat.
        """
        self.test_manager._initialise_rabbitmq()
        blocking_channel = self.test_manager.rabbitmq.channel
        method = pika.spec.Basic.Deliver(routing_key=PING_ROUTING_KEY)
        body = b'ping'
        properties = pika.spec.BasicProperties()

        try:
            self.test_manager._process_ping(blocking_channel, method,
                                            properties, body)
        except MessageWasNotDeliveredException:
            self.fail('A MessageWasNotDeliveredException should not have been '
                      'raised')

    @parameterized.expand([
        (pika.exceptions.AMQPConnectionError,
         pika.exceptions.AMQPConnectionError('test'),),
        (pika.exceptions.AMQPChannelError,
         pika.exceptions.AMQPChannelError('test'),),
        (Exception, Exception('test'),),
    ])
    @mock.patch.object(NetworkMonitorsManager, "_send_heartbeat")
    def test_process_ping_raises_unrecognised_error_if_raised_by_send_heartbeat(
            self, exception_class, exception_instance, mock_send_hb) -> None:
        mock_send_hb.side_effect = exception_instance

        self.test_manager._initialise_rabbitmq()
        blocking_channel = self.test_manager.rabbitmq.channel
        method = pika.spec.Basic.Deliver(routing_key=PING_ROUTING_KEY)
        body = 'ping'
        properties = pika.spec.BasicProperties()

        self.assertRaises(exception_class, self.test_manager._process_ping,
                          blocking_channel, method, properties, body)
