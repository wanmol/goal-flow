
from goalflow.workflow.base_workflow import BaseWorkflow
from goalflow.workflow.generated.demo_chatflow import DemoChatflow

import threading
import hashlib

from fastapi import  HTTPException, Request, status

# TODO consider encrypted storage in the future
apikey_workflow_def_map = {

    #"2999a65aa67e37253623075d60796f9a": WorkflowCarbonEmissions,
    # key is md5 of api_key "test"
    "098f6bcd4621d373cade4e832627b4f6": DemoChatflow,
}

workflow_instance = {}

lock = threading.Lock()


def get_workflow(wf_def: type[BaseWorkflow]):
    """Get or create workflow instance."""
    if wf_def in workflow_instance:
        return workflow_instance[wf_def]

    with lock:
        if wf_def in workflow_instance:
            return workflow_instance[wf_def]
        new_instance = wf_def()
        new_instance.bind_subworkflows()

        workflow_instance[wf_def] = new_instance

    return workflow_instance[wf_def]


def validate_token_and_get_wf(request: Request):
    token = request.headers.get("Authorization")
    if not token or not token.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token"
        )

    api_key = token.split(" ")[1]

    hash_object = hashlib.md5()

    data_bytes = api_key.encode()
    hash_object.update(data_bytes)

    md5_hash = hash_object.hexdigest()

    wf_def = apikey_workflow_def_map.get(md5_hash)
    if not wf_def:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token"
        )

    return get_workflow(wf_def)