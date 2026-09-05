import json

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from backcountry_sms.models import DEFAULT_MODEL_ID, NOVA_MICRO_MODEL_ID
from infrastructure.sms_assistant_stack import BackcountrySmsAssistantStack


def test_stack_creates_inbound_topic_and_echo_lambda() -> None:
    app = cdk.App()
    stack = BackcountrySmsAssistantStack(app, "TestStack")
    template = Template.from_stack(stack)

    template.resource_count_is("AWS::SNS::Topic", 2)
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {"Environment": {"Variables": Match.object_like({
            "DEPLOYMENT_ENVIRONMENT": {"Ref": "DeploymentEnvironment"},
            "TEST_MODE": {"Ref": "TestMode"},
            "SMS_DELIVERY_MODE": {"Ref": "SmsDeliveryMode"},
        })}},
    )
    template.resource_count_is("AWS::Bedrock::KnowledgeBase", 1)
    template.resource_count_is("AWS::Bedrock::DataSource", 1)
    template.resource_count_is("AWS::S3Vectors::VectorBucket", 1)
    template.resource_count_is("AWS::S3Vectors::Index", 1)
    template.resource_count_is("AWS::S3Vectors::VectorBucketPolicy", 1)
    policies = template.find_resources("AWS::IAM::Policy")
    corpus_read_policy = next(
        json.dumps(resource) for resource in policies.values()
        if "guide/ontario-provincial-parks-guide.md.metadata.json" in json.dumps(resource)
    )
    assert '"Action": "s3:GetObject"' in corpus_read_policy
    assert '"Action": "s3:GetObject*"' not in corpus_read_policy
    assert "guide/ontario-provincial-parks-guide.md\"" in corpus_read_policy
    template.has_resource_properties(
        "AWS::Bedrock::DataSource",
        {"VectorIngestionConfiguration": {"ChunkingConfiguration": {"ChunkingStrategy": "FIXED_SIZE", "FixedSizeChunkingConfiguration": {"MaxTokens": 300, "OverlapPercentage": 10}}}},
    )
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {"Environment": {"Variables": Match.object_like({"RAG_KNOWLEDGE_BASE_ID": {"Fn::GetAtt": ["OntarioParksGuideKnowledgeBase", "KnowledgeBaseId"]}})}},
    )
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {"PolicyDocument": {"Statement": Match.array_with([{
            "Action": "bedrock:Retrieve",
            "Effect": "Allow",
            "Resource": {"Fn::GetAtt": ["OntarioParksGuideKnowledgeBase", "KnowledgeBaseArn"]},
        }])}},
    )
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "backcountry_sms.handler.lambda_handler",
            "Runtime": "python3.12",
            "Timeout": 25,
            "TracingConfig": {"Mode": "Active"},
            "Environment": {
                "Variables": Match.object_like({"AWS_LAMBDA_EXEC_WRAPPER": "/opt/otel-instrument"}),
            },
        },
    )
    outputs = template.to_json()["Outputs"]
    assert outputs["OntarioParksRegion"]["Value"] == {"Ref": "AWS::Region"}
    assert outputs["OntarioParksEmbeddingModel"]["Value"] == "amazon.titan-embed-text-v2:0"
    assert outputs["OntarioParksChunking"]["Value"] == "fixed-size:300-tokens:30-token-overlap"
    assert len(outputs["OntarioParksCorpusSha256"]["Value"]) == 64
    lambda_resource = next(
        resource for resource in template.find_resources("AWS::Lambda::Function").values()
        if resource["Properties"].get("Handler") == "backcountry_sms.handler.lambda_handler"
    )
    assert "aws-otel-python" in json.dumps(lambda_resource["Properties"]["Layers"])
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "BillingMode": "PAY_PER_REQUEST",
            "KeySchema": Match.array_with([
                {"AttributeName": "user_phone_e164", "KeyType": "HASH"},
                {"AttributeName": "created_at", "KeyType": "RANGE"},
            ]),
            "SSESpecification": {"SSEEnabled": True},
            "TimeToLiveSpecification": {"AttributeName": "ttl", "Enabled": True},
        },
    )
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with([
                    {
                        "Action": "geo-places:SearchText",
                        "Effect": "Allow",
                        "Resource": "*",
                    }
                ]),
            },
        },
    )


def test_production_defaults_to_lite_and_fails_closed_for_other_models() -> None:
    app = cdk.App()
    stack = BackcountrySmsAssistantStack(app, "BackcountrySmsEcho")
    template = Template.from_stack(stack)

    template.has_parameter(
        "BedrockModelId",
        {"Default": DEFAULT_MODEL_ID, "AllowedValues": [DEFAULT_MODEL_ID, NOVA_MICRO_MODEL_ID]},
    )
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {"Environment": {"Variables": Match.object_like({"BEDROCK_MODEL_ID": {"Ref": "BedrockModelId"}})}},
    )
    policies = template.find_resources("AWS::IAM::Policy")
    bedrock_policies = [
        json.dumps(resource) for resource in policies.values()
        if "bedrock:InvokeModel" in json.dumps(resource) and "SmsEchoFunctionServiceRole" in json.dumps(resource)
    ]
    assert len(bedrock_policies) == 2
    assert any("us.amazon.nova-micro-v1:0" in policy for policy in bedrock_policies)
    assert any(resource.get("Condition") == "IsNovaLite" for resource in policies.values())
    assert any(resource.get("Condition") == "IsNovaMicro" for resource in policies.values())
    rules = template.to_json().get("Rules", {})
    assert "ProductionDeliveryGuard" in rules
    production_rule = json.dumps(rules["ProductionDeliveryGuard"])
    assert DEFAULT_MODEL_ID in production_rule
    assert "ca-central-1" in production_rule
    assert '"live"' in production_rule
    assert '"capture"' in production_rule


def test_deployment_guard_rejects_invalid_test_combinations_structurally() -> None:
    app = cdk.App()
    stack = BackcountrySmsAssistantStack(app, "BackcountrySmsEchoTest")
    template = Template.from_stack(stack)
    rule = json.dumps(template.to_json()["Rules"]["ProductionDeliveryGuard"])

    assert NOVA_MICRO_MODEL_ID in rule
    for region in ("us-east-1", "us-east-2", "us-west-2"):
        assert region in rule
    assert "ca-central-1" in rule
    assert "Only BackcountrySmsEchoTest" not in rule


def test_dedicated_test_stack_defaults_to_nova_micro() -> None:
    app = cdk.App()
    stack = BackcountrySmsAssistantStack(app, "BackcountrySmsEchoTest")
    template = Template.from_stack(stack)

    template.has_parameter("BedrockModelId", {"Default": NOVA_MICRO_MODEL_ID})


def test_rust_candidate_is_opt_in_and_not_subscribed_to_inbound_sns() -> None:
    app = cdk.App(context={"rust_candidate": True})
    template = Template.from_stack(BackcountrySmsAssistantStack(app, "BackcountrySmsEchoTest"))

    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "bootstrap",
            "Runtime": "provided.al2023",
            "Architectures": ["x86_64"],
            "Timeout": 25,
            "MemorySize": 128,
            "TracingConfig": {"Mode": "Active"},
        },
    )
    subscriptions = template.find_resources("AWS::SNS::Subscription")
    candidate_text = json.dumps(subscriptions)
    assert "RustCandidateFunction" not in candidate_text


def test_dashboard_is_single_demo_dashboard_for_every_stack() -> None:
    production_app = cdk.App()
    production_template = Template.from_stack(
        BackcountrySmsAssistantStack(production_app, "BackcountrySmsEcho")
    )
    production_dashboards = production_template.find_resources("AWS::CloudWatch::Dashboard")
    assert any(
        json.dumps(resource["Properties"]["DashboardName"]) == '"Backcountry-Demo"'
        for resource in production_dashboards.values()
    )

    test_app = cdk.App()
    test_template = Template.from_stack(
        BackcountrySmsAssistantStack(test_app, "BackcountrySmsEchoTest")
    )
    test_dashboards = test_template.find_resources("AWS::CloudWatch::Dashboard")
    test_dashboard_names = [
        json.dumps(resource["Properties"]["DashboardName"])
        for resource in test_dashboards.values()
    ]
    assert len(test_dashboard_names) == 1
    assert '"Backcountry-Demo"' in test_dashboard_names[0]


def test_dashboard_prioritizes_demo_health_calls_and_recent_redacted_events() -> None:
    app = cdk.App()
    template = Template.from_stack(BackcountrySmsAssistantStack(app, "BackcountrySmsEchoTest"))
    dashboards = template.find_resources("AWS::CloudWatch::Dashboard")
    assert len(dashboards) == 1
    dashboard = next(iter(dashboards.values()))["Properties"]
    body = json.dumps(dashboard["DashboardBody"])
    for required_text in (
        "-PT1H",
        "DEMO HEALTH",
        "Live delivery",
        "Messages and replies",
        "AI and provider calls",
        "Errors, warnings, fallbacks",
        "Recent errors and warnings",
        "Message flow",
        "Dependency health",
        "Response latency",
        "Safety and delivery boundary",
        "limit 10",
        "@message",
    ):
        assert required_text in body
    for forbidden_text in ("phone", "prompt", "coordinates", "provider payload"):
        assert forbidden_text not in body.lower()
