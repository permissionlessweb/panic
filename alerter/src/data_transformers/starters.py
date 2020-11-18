import logging
import os
import time

import pika.exceptions

from src.data_store.redis import RedisApi
from src.data_transformers.data_transformer import DataTransformer
from src.data_transformers.github import GitHubDataTransformer
from src.data_transformers.system import SystemDataTransformer
from src.utils.logging import create_logger, log_and_print


def _initialize_transformer_logger(transformer_name: str) -> logging.Logger:
    # Try initializing the logger until successful. This had to be done
    # separately to avoid instances when the logger creation failed and we
    # attempt to use it.
    while True:
        try:
            transformer_logger = create_logger(
                os.environ['TRANSFORMERS_LOG_FILE_TEMPLATE'].format(
                    transformer_name), transformer_name,
                os.environ['LOGGING_LEVEL'], rotating=True)
            break
        except Exception as e:
            msg = "!!! Error when initialising {}: {} !!!".format(
                transformer_name, e)
            # Use a dummy logger in this case because we cannot create the
            # transformer's logger.
            log_and_print(msg, logging.getLogger('DUMMY_LOGGER'))
            time.sleep(10)  # sleep 10 seconds before trying again

    return transformer_logger


def _initialize_transformer_redis(
        transformer_name: str, transformer_logger: logging.Logger) -> RedisApi:
    # Try initializing the Redis API until successful. This had to be done
    # separately to avoid instances when Redis creation failed and we
    # attempt to use it.
    while True:
        try:
            redis_db = int(os.environ['REDIS_DB'])
            redis_port = int(os.environ['REDIS_PORT'])
            redis_host = os.environ['REDIS_IP']
            unique_alerter_identifier = os.environ['UNIQUE_ALERTER_IDENTIFIER']

            redis = RedisApi(logger=transformer_logger, db=redis_db,
                             host=redis_host, port=redis_port,
                             namespace=unique_alerter_identifier)
            break
        except Exception as e:
            msg = "!!! Error when initialising {}: {} !!!".format(
                transformer_name, e)
            log_and_print(msg, transformer_logger)
            time.sleep(10)  # sleep 10 seconds before trying again

    return redis


def _initialize_system_data_transformer() -> SystemDataTransformer:
    transformer_name = 'System Data Transformer'

    transformer_logger = _initialize_transformer_logger(transformer_name)
    redis = _initialize_transformer_redis(transformer_name, transformer_logger)

    # Try initializing the system data transformer until successful
    while True:
        try:
            system_data_transformer = SystemDataTransformer(
                transformer_name, transformer_logger, redis)
            log_and_print("Successfully initialized {}"
                          .format(transformer_name), transformer_logger)
            break
        except Exception as e:
            msg = "!!! Error when initialising {}: {} !!!".format(
                transformer_name, e)
            log_and_print(msg, transformer_logger)
            time.sleep(10)  # sleep 10 seconds before trying again

    return system_data_transformer


def _initialize_github_data_transformer() -> GitHubDataTransformer:
    transformer_name = 'GitHub Data Transformer'

    transformer_logger = _initialize_transformer_logger(transformer_name)
    redis = _initialize_transformer_redis(transformer_name, transformer_logger)

    # Try initializing the github data transformer until successful
    while True:
        try:
            github_data_transformer = GitHubDataTransformer(
                transformer_name, transformer_logger, redis)
            log_and_print("Successfully initialized {}"
                          .format(transformer_name), transformer_logger)
            break
        except Exception as e:
            msg = "!!! Error when initialising {}: {} !!!".format(
                transformer_name, e)
            log_and_print(msg, transformer_logger)
            time.sleep(10)  # sleep 10 seconds before trying again

    return github_data_transformer


def start_system_data_transformer() -> None:
    system_data_transformer = _initialize_system_data_transformer()
    start_transformer(system_data_transformer)


def start_github_data_transformer() -> None:
    github_data_transformer = _initialize_github_data_transformer()
    start_transformer(github_data_transformer)


def start_transformer(transformer: DataTransformer) -> None:
    while True:
        try:
            log_and_print("{} started.".format(transformer), transformer.logger)
            transformer.start()
        except (pika.exceptions.AMQPConnectionError,
                pika.exceptions.AMQPChannelError):
            # Error would have already been logged by RabbitMQ logger.
            log_and_print("{} stopped.".format(transformer), transformer.logger)
        except Exception:
            # Close the connection with RabbitMQ if we have an unexpected
            # exception, and start again
            transformer.rabbitmq.disconnect_till_successful()
            log_and_print("{} stopped.".format(transformer), transformer.logger)
