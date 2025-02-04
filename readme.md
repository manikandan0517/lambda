1) Before pushing the code to the github add the secets and variables in the github repository
    In Secrets:
        AWS_ACCESS_KEY_ID
        AWS_SECRET_ACCESS_KEY
    In Variables:
        REGIONS
        ROLE (with all the permission enabled)
2) Then push the code to the github repository
3) The code will automatically uploaded to aws lambda
4) After that in the lambda function in configuration-> variables add the environment variables values that are specified there.
