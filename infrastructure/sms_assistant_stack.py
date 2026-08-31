"""CDK definition for the bounded Backcountry SMS assistant."""

import hashlib
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    CfnCondition,
    CfnOutput,
    CfnParameter,
    Duration,
    RemovalPolicy,
    Stack,
    Tags,
)
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cloudwatch_actions
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3_deployment
from aws_cdk import aws_s3vectors as s3vectors
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from constructs import Construct

from backcountry_sms.models import (
    ALLOWED_MODEL_IDS,
    DEFAULT_MODEL_ID,
    NOVA_MICRO_MODEL_ID,
    NOVA_MICRO_SUPPORTED_REGIONS,
)


class BackcountrySmsAssistantStack(Stack):
    """Keep the existing SMS topology and add the bounded Bedrock runtime permission."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)
        is_test_stack = construct_id == "BackcountrySmsEchoTest"
        Tags.of(self).add("Project", "backcountry-sms-ai-assistant")
        Tags.of(self).add("Stage", "5-message-context")
        Tags.of(self).add("ManagedBy", "aws-cdk")

        allowed_phone_number = CfnParameter(
            self,
            "AllowedPhoneNumber",
            type="String",
            no_echo=True,
            description="E.164 phone number allowed to receive assistant replies.",
        )
        origination_identity = CfnParameter(
            self,
            "OriginationIdentity",
            type="String",
            no_echo=True,
            description="Provisioned AWS End User Messaging SMS number or sender ID.",
        )
        alert_email = CfnParameter(
            self,
            "AlertEmail",
            type="String",
            default="",
            description="Optional email address for operational alerts.",
        )
        deployment_environment = CfnParameter(
            self,
            "DeploymentEnvironment",
            type="String",
            default="test" if is_test_stack else "production",
            allowed_values=["production", "test"],
            description="Use test only for a separately identified carrier-independent test target.",
        )
        test_mode = CfnParameter(
            self,
            "TestMode",
            type="String",
            default="true" if is_test_stack else "false",
            allowed_values=["true", "false"],
            description="Enable only on a dedicated test target and only with capture delivery.",
        )
        sms_delivery_mode = CfnParameter(
            self,
            "SmsDeliveryMode",
            type="String",
            default="capture" if is_test_stack else "live",
            allowed_values=["capture", "live"],
            description="Capture skips carrier delivery; live preserves production SMS delivery.",
        )
        bedrock_model_id = CfnParameter(
            self,
            "BedrockModelId",
            type="String",
            default=NOVA_MICRO_MODEL_ID if is_test_stack else DEFAULT_MODEL_ID,
            allowed_values=list(ALLOWED_MODEL_IDS),
            description="Bedrock model used by both bounded model calls; production is fixed to Nova 2 Lite.",
        )
        is_nova_micro = CfnCondition(
            self,
            "IsNovaMicro",
            expression=cdk.Fn.condition_equals(bedrock_model_id.value_as_string, NOVA_MICRO_MODEL_ID),
        )
        is_nova_lite = CfnCondition(
            self,
            "IsNovaLite",
            expression=cdk.Fn.condition_equals(bedrock_model_id.value_as_string, DEFAULT_MODEL_ID),
        )
        cdk.CfnRule(
            self,
            "ProductionDeliveryGuard",
            assertions=[
                cdk.CfnRuleAssertion(
                assert_=cdk.Fn.condition_or(
                    cdk.Fn.condition_and(
                        cdk.Fn.condition_equals(cdk.Aws.STACK_NAME, "BackcountrySmsEcho"),
                        cdk.Fn.condition_equals(deployment_environment.value_as_string, "production"),
                        cdk.Fn.condition_equals(test_mode.value_as_string, "false"),
                        cdk.Fn.condition_equals(sms_delivery_mode.value_as_string, "live"),
                        cdk.Fn.condition_equals(bedrock_model_id.value_as_string, DEFAULT_MODEL_ID),
                        cdk.Fn.condition_equals(cdk.Aws.REGION, "ca-central-1"),
                    ),
                    cdk.Fn.condition_and(
                        cdk.Fn.condition_equals(cdk.Aws.STACK_NAME, "BackcountrySmsEchoTest"),
                        cdk.Fn.condition_equals(deployment_environment.value_as_string, "test"),
                        cdk.Fn.condition_equals(test_mode.value_as_string, "true"),
                        cdk.Fn.condition_equals(sms_delivery_mode.value_as_string, "capture"),
                        cdk.Fn.condition_or(
                            cdk.Fn.condition_equals(bedrock_model_id.value_as_string, DEFAULT_MODEL_ID),
                            cdk.Fn.condition_and(
                                cdk.Fn.condition_equals(bedrock_model_id.value_as_string, NOVA_MICRO_MODEL_ID),
                                cdk.Fn.condition_or(*[
                                    cdk.Fn.condition_equals(cdk.Aws.REGION, region)
                                    for region in NOVA_MICRO_SUPPORTED_REGIONS
                                ]),
                            ),
                        ),
                    ),
                ),
                assert_description=(
                    "Production is ca-central-1 Lite/live only; test capture may use Lite or "
                    "Nova Micro only in a supported US source region."
                ),
                )
            ],
        )

        inbound_messages = sns.Topic(
            self,
            "InboundMessages",
            display_name="Backcountry inbound SMS",
        )
        message_context = dynamodb.Table(
            self,
            "MessageContext",
            partition_key=dynamodb.Attribute(name="user_phone_e164", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="created_at", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            time_to_live_attribute="ttl",
        )
        corpus_bucket = s3.Bucket(
            self,
            "OntarioParksGuideCorpus",
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
        )
        corpus_key = "guide/ontario-provincial-parks-guide.md"
        corpus_metadata_key = f"{corpus_key}.metadata.json"
        corpus_deployment = s3_deployment.BucketDeployment(
            self,
            "OntarioParksGuideUpload",
            sources=[s3_deployment.Source.asset("data/rag")],
            destination_bucket=corpus_bucket,
            destination_key_prefix="guide",
            retain_on_delete=True,
        )
        vector_bucket = s3vectors.CfnVectorBucket(self, "OntarioParksGuideVectors")
        vector_index = s3vectors.CfnIndex(
            self,
            "OntarioParksGuideVectorIndex",
            vector_bucket_arn=vector_bucket.attr_vector_bucket_arn,
            index_name="ontario-parks-guide",
            data_type="float32",
            dimension=1024,
            distance_metric="cosine",
            metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                non_filterable_metadata_keys=["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"],
            ),
        )
        knowledge_base_role = iam.Role(
            self,
            "OntarioParksKnowledgeBaseRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {"AWS:SourceArn": f"arn:{self.partition}:bedrock:{self.region}:{self.account}:knowledge-base/*"},
                },
            ),
        )
        knowledge_base_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:ListBucket"],
            resources=[corpus_bucket.bucket_arn],
            conditions={"StringEquals": {"s3:prefix": [corpus_key, corpus_metadata_key]}},
        ))
        knowledge_base_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[f"{corpus_bucket.bucket_arn}/{corpus_key}", f"{corpus_bucket.bucket_arn}/{corpus_metadata_key}"],
        ))
        knowledge_base_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[f"arn:{self.partition}:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0"],
        ))
        knowledge_base_role.add_to_policy(iam.PolicyStatement(
            actions=["s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors", "s3vectors:QueryVectors", "s3vectors:GetIndex"],
            resources=[vector_index.attr_index_arn],
        ))
        vector_access_policy = s3vectors.CfnVectorBucketPolicy(
            self,
            "OntarioParksGuideVectorAccess",
            vector_bucket_arn=vector_bucket.attr_vector_bucket_arn,
            policy={
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"AWS": knowledge_base_role.role_arn},
                    "Action": ["s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors", "s3vectors:QueryVectors", "s3vectors:GetIndex"],
                    "Resource": [vector_index.attr_index_arn],
                }],
            },
        )
        parks_knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "OntarioParksGuideKnowledgeBase",
            name=f"{construct_id.lower()}-ontario-parks-guide",
            description="Bounded one-file Ontario Parks guide retrieval corpus.",
            role_arn=knowledge_base_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=f"arn:{self.partition}:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0",
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    vector_bucket_arn=vector_bucket.attr_vector_bucket_arn,
                    index_arn=vector_index.attr_index_arn,
                ),
            ),
        )
        parks_knowledge_base.add_dependency(vector_index)
        parks_knowledge_base.add_dependency(vector_access_policy)
        parks_data_source = bedrock.CfnDataSource(
            self,
            "OntarioParksGuideDataSource",
            name="ontario-parks-guide-markdown",
            knowledge_base_id=parks_knowledge_base.attr_knowledge_base_id,
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=corpus_bucket.bucket_arn,
                    inclusion_prefixes=["guide/ontario-provincial-parks-guide.md"],
                ),
            ),
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="FIXED_SIZE",
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=300,
                        overlap_percentage=10,
                    ),
                ),
            ),
        )
        parks_data_source.node.add_dependency(corpus_deployment)
        log_group = logs.LogGroup(
            self,
            "SmsEchoFunctionLogGroup",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.RETAIN,
        )
        echo_function = lambda_.Function(
            self,
            "SmsEchoFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="backcountry_sms.handler.lambda_handler",
            code=lambda_.Code.from_asset(
                ".",
                exclude=[".git", ".venv", "cdk.out", "tests", "local"],
            ),
            # Named requests add one bounded geospatial lookup before the Stage 3 weather path.
            timeout=Duration.seconds(25),
            memory_size=128,
            tracing=lambda_.Tracing.ACTIVE,
            adot_instrumentation=lambda_.AdotInstrumentationConfig(
                layer_version=lambda_.AdotLayerVersion.from_python_sdk_layer_version(
                    lambda_.AdotLambdaLayerPythonSdkVersion.LATEST
                ),
                exec_wrapper=lambda_.AdotLambdaExecWrapper.INSTRUMENT_HANDLER,
            ),
            environment={
                "ALLOWED_PHONE_NUMBER": allowed_phone_number.value_as_string,
                "ORIGINATION_IDENTITY": origination_identity.value_as_string,
                "BEDROCK_MODEL_ID": bedrock_model_id.value_as_string,
                "MESSAGE_CONTEXT_TABLE": message_context.table_name,
                "DEPLOYMENT_ENVIRONMENT": deployment_environment.value_as_string,
                "TEST_MODE": test_mode.value_as_string,
                "SMS_DELIVERY_MODE": sms_delivery_mode.value_as_string,
                "RAG_KNOWLEDGE_BASE_ID": parks_knowledge_base.attr_knowledge_base_id,
            },
            log_group=log_group,
        )
        inbound_messages.add_subscription(
            subscriptions.LambdaSubscription(echo_function)
        )
        echo_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sms-voice:SendTextMessage"],
                resources=["*"],
            )
        )
        echo_function.add_to_role_policy(
            iam.PolicyStatement(actions=["bedrock:Retrieve"], resources=[parks_knowledge_base.attr_knowledge_base_arn])
        )

        alert_topic = sns.Topic(self, "OperationalAlerts", display_name="Backcountry assistant alerts")
        has_alert_email = CfnCondition(self, "HasAlertEmail", expression=cdk.Fn.condition_not(cdk.Fn.condition_equals(alert_email.value_as_string, "")))
        alert_subscription = sns.CfnSubscription(
            self,
            "AlertEmailSubscription",
            topic_arn=alert_topic.topic_arn,
            protocol="email",
            endpoint=alert_email.value_as_string,
        )
        alert_subscription.cfn_options.condition = has_alert_email
        error_alarm = cloudwatch.Alarm(
            self,
            "LambdaErrorsAlarm",
            metric=echo_function.metric_errors(period=Duration.minutes(5), statistic="Sum"),
            threshold=1,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        error_alarm.add_alarm_action(cloudwatch_actions.SnsAction(alert_topic))
        throttle_alarm = cloudwatch.Alarm(
            self,
            "LambdaThrottlesAlarm",
            metric=echo_function.metric_throttles(period=Duration.minutes(5), statistic="Sum"),
            threshold=1,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        throttle_alarm.add_alarm_action(cloudwatch_actions.SnsAction(alert_topic))
        dashboard = cloudwatch.Dashboard(
            self,
            "OperationsDashboard",
            dashboard_name=(
                f"BackcountrySmsAssistantTest-{self.region}"
                if is_test_stack
                else "BackcountrySmsAssistant"
            ),
        )
        namespace = "BackcountrySmsAssistant"
        def app_metric(name: str, statistic: str = "Sum") -> cloudwatch.Metric:
            return cloudwatch.Metric(namespace=namespace, metric_name=name, statistic=statistic)

        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Traffic and replies",
                left=[app_metric("MessagesReceived"), app_metric("RepliesSent"), app_metric("FallbackReplies")],
                right=[app_metric("MessagesIgnored")],
            ),
            cloudwatch.GraphWidget(
                title="Dependency failures",
                left=[app_metric("BedrockFailures"), app_metric("LocationFailures"), app_metric("WeatherFailures"), app_metric("SmsSendFailures")],
                right=[echo_function.metric_errors(statistic="Sum"), echo_function.metric_throttles(statistic="Sum")],
            ),
            cloudwatch.GraphWidget(
                title="Latency and usage",
                left=[app_metric("ProcessingDurationMs", "Average"), app_metric("BedrockCallsPerMessage", "Average")],
                right=[app_metric("BedrockCalls"), app_metric("WeatherCalls")],
            ),
            cloudwatch.GraphWidget(
                title="Latency percentiles",
                left=[app_metric("ProcessingDurationMs", "p50"), app_metric("ProcessingDurationMs", "p95")],
                right=[app_metric("BedrockCallDurationMs", "p95"), app_metric("WeatherCallDurationMs", "p95")],
            ),
        )
        echo_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:PutItem", "dynamodb:Query"],
                resources=[message_context.table_arn],
            )
        )
        echo_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["geo-places:SearchText"],
                resources=["*"],
            )
        )
        lite_model_policy = iam.Policy(
            self,
            "LiteModelPolicy",
            roles=[echo_function.role],
            statements=[iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:{self.partition}:bedrock:{self.region}:{self.account}:inference-profile/{DEFAULT_MODEL_ID}",
                    *[
                        f"arn:{self.partition}:bedrock:{region}::foundation-model/amazon.nova-2-lite-v1:0"
                        for region in (self.region, *NOVA_MICRO_SUPPORTED_REGIONS)
                    ],
                ],
            )],
        )
        lite_model_policy.node.default_child.cfn_options.condition = is_nova_lite

        micro_model_policy = iam.Policy(
            self,
            "MicroModelPolicy",
            roles=[echo_function.role],
            statements=[iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:{self.partition}:bedrock:{self.region}:{self.account}:inference-profile/{NOVA_MICRO_MODEL_ID}",
                    *[
                        f"arn:{self.partition}:bedrock:{region}::foundation-model/amazon.nova-micro-v1:0"
                        for region in NOVA_MICRO_SUPPORTED_REGIONS
                    ],
                ],
            )],
        )
        micro_model_policy.node.default_child.cfn_options.condition = is_nova_micro
        echo_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )
        dashboard.add_widgets(
            cloudwatch.TextWidget(
                width=24,
                height=3,
                markdown=(
                    "### Trace investigation\n"
                    "Open the [AWS X-Ray service map]("
                    f"https://{self.region}.console.aws.amazon.com/xray/home?region={self.region}#/service-map"
                    ") for sampled invocation waterfalls. Traces contain only bounded operation, "
                    "provider, outcome, and error-type attributes; CloudWatch metrics remain the aggregate source."
                ),
            )
        )

        CfnOutput(
            self,
            "InboundSmsTopicArn",
            value=inbound_messages.topic_arn,
            description="Configure this as the SMS number's two-way SMS SNS destination.",
        )
        corpus_sha256 = hashlib.sha256(
            Path("data/rag/ontario-provincial-parks-guide.md").read_bytes()
        ).hexdigest()
        CfnOutput(self, "OntarioParksKnowledgeBaseId", value=parks_knowledge_base.attr_knowledge_base_id)
        CfnOutput(self, "OntarioParksDataSourceId", value=parks_data_source.attr_data_source_id)
        CfnOutput(self, "OntarioParksCorpusUri", value=f"s3://{corpus_bucket.bucket_name}/guide/ontario-provincial-parks-guide.md")
        CfnOutput(self, "OntarioParksCorpusSha256", value=corpus_sha256)
        CfnOutput(self, "OntarioParksRegion", value=self.region, description="Region containing the Ontario Parks Knowledge Base.")
        CfnOutput(self, "OntarioParksEmbeddingModel", value="amazon.titan-embed-text-v2:0", description="Embedding model used by the Knowledge Base.")
        CfnOutput(self, "OntarioParksChunking", value="fixed-size:300-tokens:30-token-overlap", description="Fixed chunking settings for the corpus.")
