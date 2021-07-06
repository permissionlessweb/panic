# Exchanges
CONFIG_EXCHANGE = 'config'
RAW_DATA_EXCHANGE = 'raw_data'
STORE_EXCHANGE = 'store'
ALERT_EXCHANGE = 'alert'
HEALTH_CHECK_EXCHANGE = 'health_check'

# Exchange Types
TOPIC = 'topic'
DIRECT = 'direct'

# Queues
CONFIGS_MANAGER_HEARTBEAT_QUEUE = "configs_manager_heartbeat_queue"
GH_MON_MAN_HEARTBEAT_QUEUE_NAME = 'github_monitors_manager_heartbeat_queue'
GH_MON_MAN_CONFIGS_QUEUE_NAME = 'github_monitors_manager_configs_queue'
SYS_MON_MAN_HEARTBEAT_QUEUE_NAME = 'system_monitors_manager_heartbeat_queue'
SYS_MON_MAN_CONFIGS_QUEUE_NAME = 'system_monitors_manager_configs_queue'
NODE_MON_MAN_CONFIGS_QUEUE_NAME = 'node_monitors_manager_configs_queue'
NODE_MON_MAN_HEARTBEAT_QUEUE_NAME = 'node_monitors_manager_heartbeat_queue'
GITHUB_DT_INPUT_QUEUE_NAME = 'github_data_transformer_input_queue'
SYSTEM_DT_INPUT_QUEUE_NAME = 'system_data_transformer_input_queue'
CL_NODE_DT_INPUT_QUEUE_NAME = 'chainlink_node_data_transformer_input_queue'
DT_MAN_HEARTBEAT_QUEUE_NAME = 'data_transformers_manager_heartbeat_queue'
SYS_ALERTER_INPUT_QUEUE_NAME_TEMPLATE = "system_alerter_input_queue_{}"
GITHUB_ALERTER_INPUT_QUEUE_NAME = 'github_alerter_input_queue'
CL_NODE_ALERTER_INPUT_QUEUE_NAME = 'cl_node_alerter_input_queue'
CL_NODE_ALERTER_CONFIGS_QUEUE_NAME = 'cl_node_alerter_configs_queue'
SYS_ALERTERS_MAN_HEARTBEAT_QUEUE_NAME = \
    'system_alerters_manager_heartbeat_queue'
SYS_ALERTERS_MANAGER_CONFIGS_QUEUE_NAME = \
    'system_alerters_manager_configs_queue'
GH_ALERTERS_MAN_HEARTBEAT_QUEUE_NAME = 'github_alerters_manager_heartbeat_queue'
ALERT_ROUTER_CONFIGS_QUEUE_NAME = 'alert_router_configs_queue'
ALERT_ROUTER_INPUT_QUEUE_NAME = 'alert_router_input_queue'
ALERT_ROUTER_HEARTBEAT_QUEUE_NAME = 'alert_router_heartbeat_queue'
ALERT_STORE_INPUT_QUEUE_NAME = 'alert_store_input_queue'
CONFIGS_STORE_INPUT_QUEUE_NAME = 'configs_store_input_queue'
GITHUB_STORE_INPUT_QUEUE_NAME = 'github_store_input_queue'
SYSTEM_STORE_INPUT_QUEUE_NAME = 'system_store_input_queue'
CL_NODE_STORE_INPUT_QUEUE_NAME = 'chainlink_node_store_input_queue'
DATA_STORES_MAN_HEARTBEAT_QUEUE_NAME = 'data_stores_manager_heartbeat_queue'
CHAN_ALERTS_HAN_INPUT_QUEUE_NAME_TEMPLATE = '{}_alerts_handler_input_queue'
CHAN_CMDS_HAN_HB_QUEUE_NAME_TEMPLATE = '{}_commands_handler_heartbeat_queue'
CHANNELS_MANAGER_CONFIGS_QUEUE_NAME = 'channels_manager_configs_queue'
CHANNELS_MANAGER_HEARTBEAT_QUEUE_NAME = 'channels_manager_heartbeat_queue'
HB_HANDLER_HEARTBEAT_QUEUE_NAME = 'heartbeat_handler_heartbeat_queue'

# Chainlink related queue names
CHAINLINK_ALERTER_MAN_HEARTBEAT_QUEUE_NAME = \
    'chainlink_alerter_manager_heartbeat_queue'
CHAINLINK_ALERTER_MAN_CONFIGS_QUEUE_NAME = \
    'chainlink_alerter_manager_configs_queue'


# Routing Keys
SYSTEM_RAW_DATA_ROUTING_KEY = 'system'
CHAINLINK_NODE_RAW_DATA_ROUTING_KEY = 'node.chainlink'
GITHUB_RAW_DATA_ROUTING_KEY = 'github'
GH_MON_MAN_CONFIGS_ROUTING_KEY_CHAINS = 'chains.*.*.github_repos_config'
GH_MON_MAN_CONFIGS_ROUTING_KEY_GEN = 'general.github_repos_config'
SYS_MON_MAN_CONFIGS_ROUTING_KEY_CHAINS_SYS = 'chains.*.*.systems_config'
SYS_MON_MAN_CONFIGS_ROUTING_KEY_CHAINS_NODES = 'chains.*.*.nodes_config'
SYS_MON_MAN_CONFIGS_ROUTING_KEY_GEN = 'general.systems_config'
NODE_MON_MAN_CONFIGS_ROUTING_KEY_CHAINS = 'chains.*.*.nodes_config'
GITHUB_TRANSFORMED_DATA_ROUTING_KEY = 'transformed_data.github'
SYSTEM_TRANSFORMED_DATA_ROUTING_KEY_TEMPLATE = 'transformed_data.system.{}'
CL_NODE_TRANSFORMED_DATA_ROUTING_KEY = 'transformed_data.node.chainlink'
SYSTEM_ALERT_ROUTING_KEY = 'alert.system'
GITHUB_ALERT_ROUTING_KEY = 'alert.github'
CL_NODE_ALERT_ROUTING_KEY = 'alert.node.chainlink'
ALERTS_CONFIGS_ROUTING_KEY_CHAIN = 'chains.*.*.alerts_config'
ALERTS_CONFIGS_ROUTING_KEY_GEN = 'general.alerts_config'
ALERT_ROUTER_CONFIGS_ROUTING_KEY = 'channels.*'
ALERT_ROUTER_INPUT_ROUTING_KEY = 'alert.*'
ALERT_STORE_INPUT_ROUTING_KEY = 'alert'
CONFIGS_STORE_INPUT_ROUTING_KEY = '#'
SYSTEM_STORE_INPUT_ROUTING_KEY = 'transformed_data.system.*'
CHANNEL_HANDLER_INPUT_ROUTING_KEY_TEMPLATE = 'channel.{}'
CONSOLE_HANDLER_INPUT_ROUTING_KEY = "channel.console"
LOG_HANDLER_INPUT_ROUTING_KEY = 'channel.log'
CHANNELS_MANAGER_CONFIGS_ROUTING_KEY = 'channels.*'
PING_ROUTING_KEY = 'ping'
HEARTBEAT_INPUT_ROUTING_KEY = 'heartbeat.*'
HEARTBEAT_OUTPUT_WORKER_ROUTING_KEY = 'heartbeat.worker'
HEARTBEAT_OUTPUT_MANAGER_ROUTING_KEY = 'heartbeat.manager'
CL_ALERTS_CONFIGS_ROUTING_KEY = 'chains.chainlink.*.alerts_config'
