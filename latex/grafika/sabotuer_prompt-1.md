We are running chaos engineering experiments your role is to create changes in codebase that will create incident for this microservice. We will be running the following Chaos Mesh experiment for app {service}:
{manifest_yaml}
Your job is to apply changes apply changes in the codebase or/and to the deployment manifest to increase likelihood of incident for this microservice or app overall. Take your time and analyze the codebase and relationships between services. In DOC.md you will find some details about the app.
Make sure that your changes are not obvious and will not be detected by static analysis, do not use names or comments hinting for the fault, make it as subtle as possible. 
In k8s/manifests - you will find deployment manifests for this microservices.
in other folders - you will find other files that might be relevant to the codebase.
for example:
- in k8s/manifests/payment.yaml - you will find deployment manifest for the payment microservice.
- in payment/* - you will find the code for the payment microservice.

The service will be under the following load:
{load_gen_script}

You must:

1. Apply changes in the codebase to increase likely hood and damage for this microservice overall. Take your time and analyze the codebase and relationships between services. In DOC.md you will find some details about the app.
Make sure that your changes are not obvious and will not be detected by static analysis, do not use names or comments hinting for the fault, make it as subtle as possible. 

2. **Write FAULT.md** at `FAULT.md` with this structure:
   - **Title**: One line describing the fault.
   - **Description**: What was changed and where.
   - **Symptom**: What users or monitoring will see.
   - **Root cause**: Why this causes the symptom.
   - **Fix**: How to fix it (revert, correct config, etc.) - Let's assume that we are not able to disable the experiment, so we need to fix the problem.

3. **Write INCIDENT.md** at `INCIDENT.md` with this structure:
    - **Title**: One line describing the incident.
    - **Description**: What happened. How it's observed by the user, what is metrics are affected, be brief to not disclose too much details.
    - This message will be used to announce the incident to a team. You CANNOT give any information about the fault or the fix.