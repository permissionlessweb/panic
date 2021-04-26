import copy
import json
import logging
from datetime import datetime
from http.client import IncompleteRead
from typing import List, Dict

import pika
from requests.exceptions import (ConnectionError as ReqConnectionError,
                                 ReadTimeout, ChunkedEncodingError,
                                 MissingSchema, InvalidSchema, InvalidURL)
from urllib3.exceptions import ProtocolError

from src.configs.nodes.chainlink import ChainlinkNodeConfig
from src.message_broker.rabbitmq import RabbitMQApi
from src.monitors.monitor import Monitor
from src.utils.constants import RAW_DATA_EXCHANGE
from src.utils.data import get_prometheus_metrics_data
from src.utils.exceptions import (NoMonitoringSourceGivenException,
                                  NodeIsDownException, PANICException,
                                  DataReadingException, InvalidUrlException,
                                  MetricNotFoundException)


class ChainlinkNodeMonitor(Monitor):
    def __init__(self, monitor_name: str, node_config: ChainlinkNodeConfig,
                 logger: logging.Logger, monitor_period: int,
                 rabbitmq: RabbitMQApi) -> None:
        if len(node_config.node_prometheus_urls) == 0:
            raise NoMonitoringSourceGivenException(node_config.node_name)

        super().__init__(monitor_name, logger, monitor_period, rabbitmq)
        self._node_config = node_config
        self._metrics_to_monitor = ['head_tracker_current_head',
                                    'head_tracker_heads_in_queue',
                                    'head_tracker_heads_received_total',
                                    'head_tracker_num_heads_dropped_total',
                                    'job_subscriber_subscriptions',
                                    'max_unconfirmed_blocks',
                                    'process_start_time_seconds',
                                    'tx_manager_num_gas_bumps_total',
                                    'tx_manager_gas_bump_exceeds_limit_total',
                                    'unconfirmed_transactions',
                                    'eth_balance',
                                    'run_status_update_total',
                                    ]
        self._last_source_used = node_config.node_prometheus_urls[0]

    @property
    def node_config(self) -> ChainlinkNodeConfig:
        return self._node_config

    @property
    def metrics_to_monitor(self) -> List[str]:
        return self._metrics_to_monitor

    @property
    def last_source_used(self) -> str:
        return self._last_source_used

    def _display_data(self, data: Dict) -> str:
        # This function assumes that the data has been obtained and processed
        # successfully by the monitor
        return "head_tracker_current_head={}, " \
               "head_tracker_heads_in_queue={}, " \
               "head_tracker_heads_received_total={}, " \
               "head_tracker_num_heads_dropped_total={}, " \
               "job_subscriber_subscriptions={}, max_unconfirmed_blocks={}, " \
               "process_start_time_seconds={}, " \
               "tx_manager_num_gas_bumps_total={}, " \
               "tx_manager_gas_bump_exceeds_limit_total={}, " \
               "unconfirmed_transactions={}, ethereum_addresses={}," \
               "run_status_update_total_errors={}" \
               "".format(data['head_tracker_current_head'],
                         data['head_tracker_heads_in_queue'],
                         data['head_tracker_heads_received_total'],
                         data['head_tracker_num_heads_dropped_total'],
                         data['job_subscriber_subscriptions'],
                         data['max_unconfirmed_blocks'],
                         data['process_start_time_seconds'],
                         data['tx_manager_num_gas_bumps_total'],
                         data['tx_manager_gas_bump_exceeds_limit_total'],
                         data['unconfirmed_transactions'],
                         data['ethereum_addresses'],
                         data['run_status_update_total_errors'])

    def _get_data(self) -> Dict:
        """
        This method will try to get all the metrics from the chainlink node
        which is online. It first tries to get the metrics from the last source
        used, if it fails, it tries to get the data from the back-up nodes.
        If it can't connect with any node, it will raise a NodeIsDownException.
        If it connected with a node, and the node raised another error, it will
        raise that error because it means that the correct node was selected but
        another issue was found.
        :return: A Dict containing all the metric values.
        """
        try:
            return get_prometheus_metrics_data(self.last_source_used,
                                               self.metrics_to_monitor,
                                               self.logger, verify=False)
        except (ReqConnectionError, ReadTimeout):
            self.logger.debug("Could not connect with %s. Will try to obtain "
                              "the metrics from another backup source.",
                              self.last_source_used)

        for source in self.node_config.node_prometheus_urls:
            try:
                data = get_prometheus_metrics_data(source,
                                                   self.metrics_to_monitor,
                                                   self.logger, verify=False)
                self._last_source_used = source
                return data
            except (ReqConnectionError, ReadTimeout):
                self.logger.debug(
                    "Could not connect with %s. Will try to obtain "
                    "the metrics from another backup source.",
                    self.last_source_used)

        raise NodeIsDownException(self.node_config.node_name)

    def _process_error(self, error: PANICException) -> Dict:
        processed_data = {
            'error': {
                'meta_data': {
                    'monitor_name': self.monitor_name,
                    'node_name': self.node_config.node_name,
                    'source_used': self.last_source_used,
                    'node_id': self.node_config.node_id,
                    'node_parent_id': self.node_config.parent_id,
                    'time': datetime.now().timestamp()
                },
                'message': error.message,
                'code': error.code,
            }
        }

        return processed_data

    def _process_retrieved_data(self, data: Dict) -> Dict:
        data_copy = copy.deepcopy(data)

        # Add some meta-data to the processed data
        processed_data = {
            'result': {
                'meta_data': {
                    'monitor_name': self.monitor_name,
                    'node_name': self.node_config.node_name,
                    'source_used': self.last_source_used,
                    'node_id': self.node_config.node_id,
                    'node_parent_id': self.node_config.parent_id,
                    'time': datetime.now().timestamp()
                },
                'data': {},
            }
        }

        one_value_metrics = self.metrics_to_monitor[:-2]
        # Add each one value metric and its value to the processed data
        for metric in one_value_metrics:
            value = data_copy[metric]
            self.logger.debug("%s %s: %s", self.node_config, metric, value)
            processed_data['result']['data'][metric] = value

        # Add the ethereum balance of all addresses to the processed data
        processed_data['result']['data']['ethereum_addresses'] = {}
        ethereum_addresses_dict = processed_data['result']['data'][
            'ethereum_addresses']
        for eth_address in self.node_config.ethereum_addresses:
            for _, data_subset in enumerate(data_copy['eth_balance']):
                if json.loads(data_subset)['account'] == eth_address:
                    ethereum_addresses_dict[eth_address] = data_copy[
                        'eth_balance'][data_subset]

        # Add the number of error job runs to the processed data
        no_of_error_job_runs = 0
        for _, data_subset in enumerate(data_copy['run_status_update_total']):
            if json.loads(data_subset)['status'] == 'errored':
                no_of_error_job_runs += 1

        self.logger.debug("%s run_status_update_total_errors: %s",
                          self.node_config, no_of_error_job_runs)
        processed_data['result']['data'][
            'run_status_update_total_errors'] = no_of_error_job_runs

        return processed_data

    def _send_data(self, data: Dict) -> None:
        self.rabbitmq.basic_publish_confirm(
            exchange=RAW_DATA_EXCHANGE, routing_key='node.chainlink', body=data,
            is_body_dict=True, properties=pika.BasicProperties(delivery_mode=2),
            mandatory=True)
        self.logger.debug("Sent data to '%s' exchange", RAW_DATA_EXCHANGE)

    def _monitor(self) -> None:
        data_retrieval_exception = None
        data = None
        data_retrieval_failed = False
        try:
            data = self._get_data()
        except NodeIsDownException as e:
            data_retrieval_failed = True
            data_retrieval_exception = e
            self.logger.error("Metrics could not be obtained from any source.")
            self.logger.exception(data_retrieval_exception)
        except (IncompleteRead, ChunkedEncodingError, ProtocolError):
            data_retrieval_failed = True
            data_retrieval_exception = DataReadingException(
                self.monitor_name, self.last_source_used)
            self.logger.error("Error when retrieving data from %s",
                              self.last_source_used)
            self.logger.exception(data_retrieval_exception)
        except (InvalidURL, InvalidSchema, MissingSchema):
            data_retrieval_failed = True
            data_retrieval_exception = InvalidUrlException(
                self.last_source_used)
            self.logger.error("Error when retrieving data from %s",
                              self.last_source_used)
            self.logger.exception(data_retrieval_exception)
        except MetricNotFoundException as e:
            data_retrieval_failed = True
            data_retrieval_exception = e
            self.logger.error("Error when retrieving data from %s",
                              self.last_source_used)
            self.logger.exception(data_retrieval_exception)

        try:
            processed_data = self._process_data(data, data_retrieval_failed,
                                                data_retrieval_exception)
        except Exception as error:
            self.logger.error("Error when processing data obtained from %s",
                              self.last_source_used)
            self.logger.exception(error)
            # Do not send data if we experienced processing errors
            return

        self._send_data(processed_data)

        if not data_retrieval_failed:
            # Only output the gathered data if there was no error
            self.logger.info(self._display_data(
                processed_data['result']['data']))

        # Send a heartbeat only if the entire round was successful
        heartbeat = {
            'component_name': self.monitor_name,
            'is_alive': True,
            'timestamp': datetime.now().timestamp()
        }
        self._send_heartbeat(heartbeat)


# node_config = ChainlinkNodeConfig('test', 'test', 'test', True,
#                                   ['https://172.16.152.160:1002/metrics'],
#                                   ["0xaDb83Abbf7A8987AfB76DB33Ed2855A07f5497C7"])
# monitor = ChainlinkNodeMonitor('test_monitor', node_config,
#                                logging.getLogger('Dummy'), 10, None)
# print(monitor._process_retrieved_data(monitor._get_data()))
