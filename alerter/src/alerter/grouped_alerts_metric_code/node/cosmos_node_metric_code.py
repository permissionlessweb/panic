from ..grouped_alerts_metric_code import GroupedAlertsMetricCode


class GroupedCosmosNodeAlertsMetricCode(GroupedAlertsMetricCode):
    NodeIsDown = 'cosmos_node_is_down'
    ValidatorWasSlashed = 'cosmos_node_slashed'
    NodeIsSyncing = 'cosmos_node_syncing'
    NodeIsNotPeeredWithSentinel = 'cosmos_node_is_not_peered_with_sentinel'
    ValidatorIsNotActive = 'cosmos_node_active'
    ValidatorIsJailed = 'cosmos_node_jailed'
    BlocksMissedThreshold = 'cosmos_node_blocks_missed'
    NoChangeInHeight = 'cosmos_node_change_in_height'
    BlockHeightDifferenceThreshold = 'cosmos_node_height_difference'
    PrometheusInvalidUrl = 'cosmos_node_prometheus_url_invalid'
    CosmosRestInvalidUrl = 'cosmos_node_cosmos_rest_url_invalid'
    CometbftRPCInvalidUrl = 'cosmos_node_cometbft_rpc_url_invalid'
    PrometheusSourceIsDown = 'cosmos_node_prometheus_is_down'
    CosmosRestSourceIsDown = 'cosmos_node_cosmos_rest_is_down'
    CometbftRPCSourceIsDown = 'cosmos_node_cometbft_rpc_is_down'
    NoSyncedCosmosRestSource = 'cosmos_node_no_synced_cosmos_rest_source'
    NoSyncedCometbftRPCSource = 'cosmos_node_no_synced_cometbft_rpc_source'
    CosmosRestDataNotObtained = 'cosmos_node_cosmos_rest_data_not_obtained'
    CometbftRPCDataNotObtained = (
        'cosmos_node_cometbft_rpc_data_not_obtained'
    )
    MetricNotFound = 'cosmos_node_metric_not_found'
