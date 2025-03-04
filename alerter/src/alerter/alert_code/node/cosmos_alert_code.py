from ..alert_code import AlertCode


class CosmosNodeAlertCode(AlertCode):
    NodeWentDownAtAlert = 'cosmos_node_alert_1'
    NodeBackUpAgainAlert = 'cosmos_node_alert_2'
    NodeStillDownAlert = 'cosmos_node_alert_3'
    ValidatorWasSlashedAlert = 'cosmos_node_alert_4'
    NodeIsSyncingAlert = 'cosmos_node_alert_5'
    NodeIsNoLongerSyncingAlert = 'cosmos_node_alert_6'
    ValidatorIsNotActiveAlert = 'cosmos_node_alert_7'
    ValidatorIsActiveAlert = 'cosmos_node_alert_8'
    ValidatorIsJailedAlert = 'cosmos_node_alert_9'
    ValidatorIsNoLongerJailedAlert = 'cosmos_node_alert_10'
    BlocksMissedIncreasedAboveThresholdAlert = 'cosmos_node_alert_11'
    BlocksMissedDecreasedBelowThresholdAlert = 'cosmos_node_alert_12'
    NoChangeInHeightAlert = 'cosmos_node_alert_13'
    BlockHeightUpdatedAlert = 'cosmos_node_alert_14'
    BlockHeightDifferenceIncreasedAboveThresholdAlert = 'cosmos_node_alert_15'
    BlockHeightDifferenceDecreasedBelowThresholdAlert = 'cosmos_node_alert_16'
    PrometheusInvalidUrlAlert = 'cosmos_node_alert_17'
    PrometheusValidUrlAlert = 'cosmos_node_alert_18'
    CosmosRestInvalidUrlAlert = 'cosmos_node_alert_19'
    CosmosRestValidUrlAlert = 'cosmos_node_alert_20'
    CometbftRPCInvalidUrlAlert = 'cosmos_node_alert_21'
    CometbftRPCValidUrlAlert = 'cosmos_node_alert_22'
    PrometheusSourceIsDownAlert = 'cosmos_node_alert_23'
    PrometheusSourceStillDownAlert = 'cosmos_node_alert_24'
    PrometheusSourceBackUpAgainAlert = 'cosmos_node_alert_25'
    CosmosRestSourceIsDownAlert = 'cosmos_node_alert_26'
    CosmosRestSourceStillDownAlert = 'cosmos_node_alert_27'
    CosmosRestSourceBackUpAgainAlert = 'cosmos_node_alert_28'
    CometbftRPCSourceIsDownAlert = 'cosmos_node_alert_29'
    CometbftRPCSourceStillDownAlert = 'cosmos_node_alert_30'
    CometbftRPCSourceBackUpAgainAlert = 'cosmos_node_alert_31'
    ErrorNoSyncedCosmosRestDataSourcesAlert = 'cosmos_node_alert_32'
    SyncedCosmosRestDataSourcesFoundAlert = 'cosmos_node_alert_33'
    ErrorNoSyncedCometbftRPCDataSourcesAlert = 'cosmos_node_alert_34'
    SyncedCometbftRPCDataSourcesFoundAlert = 'cosmos_node_alert_35'
    CosmosRestServerDataCouldNotBeObtainedAlert = 'cosmos_node_alert_36'
    CosmosRestServerDataObtainedAlert = 'cosmos_node_alert_37'
    CometbftRPCDataCouldNotBeObtainedAlert = 'cosmos_node_alert_38'
    CometbftRPCDataObtainedAlert = 'cosmos_node_alert_39'
    MetricNotFoundErrorAlert = 'cosmos_node_alert_40'
    MetricFoundAlert = 'cosmos_node_alert_41'
    NodeIsNotPeeredWithSentinelAlert = 'cosmos_node_alert_42'
    NodeIsPeeredWithSentinelAlert = 'cosmos_node_alert_43'
