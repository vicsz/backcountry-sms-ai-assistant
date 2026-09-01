import aws_cdk as cdk

from infrastructure.sms_assistant_stack import BackcountrySmsAssistantStack

app = cdk.App()
target = app.node.try_get_context("target") or "test"
if target != "test":
    raise ValueError("this repository has one deployable environment; use context target=test")
BackcountrySmsAssistantStack(app, "BackcountrySmsEchoTest")
app.synth()
