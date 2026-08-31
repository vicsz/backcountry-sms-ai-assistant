import aws_cdk as cdk

from infrastructure.sms_assistant_stack import BackcountrySmsAssistantStack

app = cdk.App()
target = app.node.try_get_context("target") or "production"
stack_id = {"production": "BackcountrySmsEcho", "test": "BackcountrySmsEchoTest"}.get(target)
if stack_id is None:
    raise ValueError("context target must be production or test")
BackcountrySmsAssistantStack(app, stack_id)
app.synth()
