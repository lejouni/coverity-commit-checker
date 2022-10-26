# -*- coding: utf-8 -*-
#
# Script for helping Coverity usage in CI/CD tools.
#
import json
import requests
import logging
import argparse
import pymsteams
from os.path import abspath, exists
import os
import sys
import datetime
from timeit import default_timer as timer


__author__ = "Jouni Lehto"
__versionro__="0.0.2"

#Global variables
args = ""

#
# Get the latest snapshotID for the given stream. This will use the Coverity API endpoint (/api/v2/streams/stream/snapshots).
# streamName = Projects stream name which the latest snapshotID is returned.
#  
def getLatestComparableSnapshotIDByStream(streamName):
    if streamName:
        headers = {'Accept': 'application/json'}
        endpoint = '/api/v2/streams/stream/snapshots'
        currentDate = datetime.datetime.now() + datetime.timedelta(days=1)
        params = f'?idType=byName&name={streamName}&hasSummaries=true&lastBeforeCodeVersionDate={currentDate.year}-{currentDate.month}-{currentDate.day}&locale=en_us'
        logging.debug(args.coverity_url + endpoint + params)
        r = requests.get(args.coverity_url + endpoint + params, headers=headers, auth=(args.username, args.password))
        if( r.status_code == 200 ):
            data = json.loads(r.content)
            if(logging.getLogger().isEnabledFor(logging.DEBUG)):
                logging.debug(f'Latest snapshotID for stream {streamName} is {data["snapshotsForStream"][0]["id"]}')
            return data['snapshotsForStream'][0]['id']
        else:
            logging.error(f'Coverity API endpoint (/api/v2/streams/stream/snapshots) request failed with error code: {r.status_code}')

#
# Get all findings for given project and snapshotID. This will use the Coverity API endpoint (/api/v2/issues/search).
# snapshotID = projects stream snapshotID which findings will be returned
#
def getFindingsBySnapshotID(snapshotID, project_name):
    start = timer()
    if project_name and snapshotID:
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        endpoint = '/api/v2/issues/search?includeColumnLabels=false&locale=en_us&offset=0&queryType=bySnapshot&rowCount=-1&sortOrder=asc'
        params = {"filters": [{"columnKey": "project","matchMode": "oneOrMoreMatch","matchers": [{"class": "Project","name": project_name,
                            "type": "nameMatcher"}]}],"columns": ["mergeKey"],"snapshotScope": {
                            "show": {"scope": snapshotID}}}
        r = requests.post(args.coverity_url + endpoint, headers=headers, auth=(args.username, args.password), json=params)
        logging.debug(f'params for /api/v2/issues/search: {params}')
        if(logging.getLogger().isEnabledFor(logging.DEBUG)):
            end = timer()
            logging.debug(f"Coverity endpoint (/api/v2/issues/search) request took: {end - start} seconds.")
        if( r.status_code == 200 ):
            data = json.loads(r.content)
            mergeKeys = []
            for issue in data['rows']:
                for key in issue:
                    if key['key'] == 'mergeKey': mergeKeys.append(key['value'])
            return mergeKeys
        else:
            logging.error(f'FindingsBySnapshotID failed: {json.dumps(r, indent=3)}')

#
# Get the findings based on give viewID. Use Coverity API endpoint (/api/v2/views/viewContents/).
#
def getFindingsByView(projectID):
    headers = {'Accept': 'application/json'}
    endpoint = f'/api/v2/views/viewContents/{args.viewID}?projectId={projectID}&rowCount=-1&offset=0&sortKey=mergeKey&sortOrder=desc&locale=en_us'
    r = requests.get(args.coverity_url + endpoint, headers=headers, auth=(args.username, args.password))
    if( r.status_code == 200 ):
        data = json.loads(r.content)
        mergeKeys = []
        for issue in data['rows']:
            for key in issue:
                if key['key'] == 'mergeKey': mergeKeys.append(key['value'])
        return mergeKeys

#
# Get proejct name for the given stream. Use Coverity API endpoint (/api/v2/streams/).
#
def getProjectNameforStream():
    headers = {'Accept': 'application/json'}
    endpoint = f'/api/v2/streams/{args.stream_name}?locale=en_us'
    r = requests.get(args.coverity_url + endpoint, headers=headers, auth=(args.username, args.password))
    if( r.status_code == 200 ):
        data = json.loads(r.content)
        if(logging.getLogger().isEnabledFor(logging.DEBUG)):
            logging.debug(f'Project name for stream: {args.stream_name} is {data["streams"][0]["primaryProjectName"]}')
        return data["streams"][0]["primaryProjectName"]
    else:
        raise SystemExit(f'No project name found for stream {args.stream_name}, error: {r.content}')

#
# Get the projectID with the given project name. Use Coverity API endpoint (/api/v2/projects/)
#
def getProjectID(project_name):
    headers = {'Accept': 'application/json'}
    endpoint = f'/api/v2/projects/{project_name}?includeChildren=false&includeStreams=false&locale=en_us'
    r = requests.get(args.coverity_url + endpoint, headers=headers, auth=(args.username, args.password))
    if( r.status_code == 200 ):
        data = json.loads(r.content)
        if(logging.getLogger().isEnabledFor(logging.DEBUG)):
            logging.debug(f'ProjectID for project: {project_name} is {data["projects"][0]["projectKey"]}')
        return data["projects"][0]["projectKey"]
    else:
        raise SystemExit(f'No projectID found for project {project_name}, error: {r.content}')

#
# Will create an JSON output file with Coverity command cov-format-errors and using flag --json-output-v10 and will remove the file
# in the end of method call. This will return all the mergeKeys what the current analysis has found and are in given intermediate directory.
#
def getAnalysisMergeKeys():
    previewFileName = f"{args.intermediate_dir}{os.path.sep}coverity_analysis_results.json"
    exportCommand = f"{args.coverity_home}cov-format-errors --dir {args.intermediate_dir} --json-output-v10 {previewFileName}"
    os.system(exportCommand)
    if ( exists(previewFileName) ):
        previewData = json.load(open(previewFileName, "r"))
        issues = previewData["issues"]
        mergeKeys = []
        for issue in issues:
            mergeKeys.append(issue['mergeKey'])
        # os.remove(previewFileName)
        return mergeKeys
    return []

# 
# Will compare the given lists of mergeKeys. If analysisMergeKeys has values that not in snapshotMergeKeys, then we have some new findings.
# But if snapshotMergeKeys has values that the analysisMergeKeys doesn't have, then we have fixed some findings which the latest snapshot has.
# Will return True if there is a need to run full analysis and False if not, which will mean that there are no changed to compared the
# latest snapshot of the given project/stream.
#
def checkFindings(analysisMergeKeys, snapshotMergeKeys):
    # Lists are not the same -> we have new findings (analysisMergeKeys has mergeKeys which are not in snapshotMergeKeys) 
    # or we have fixed findings (snapshotMergeKeys has mergeKeys which are not in analysisMergeKeys)
    return set(snapshotMergeKeys) - set(analysisMergeKeys), set(analysisMergeKeys) - set(snapshotMergeKeys)

#
# This method is checking the emit percentage from given Coverity log file
# and if the emit percentage is lower than given threshold.
#
def checkEmitPrecentage():
    fileWithPath = abspath(args.intermediate_dir + os.path.sep + args.build_log_file)
    if( exists(fileWithPath) ):
        with open(fileWithPath) as openfile:
            for line in openfile:
                if ("compilation units (" in line):
                    if(logging.getLogger().isEnabledFor(logging.DEBUG)):
                        logging.debug(f'Emit percentage was: {line[line.find("Emitted"):-1]}')
                    if (int((line[line.find('(')+1:line.find('%)')])) < args.emit_threshold):
                        return False, line[line.find('Emitted'):-1]
    else:
        logging.error(f"File: {fileWithPath} not found!")
        return False, f"File: {fileWithPath} not found!"
    return True, f'was in the give threshold: {args.emit_threshold}'

#
# Will exit with -1, if "--break_build=True". This can be used to break the build in CI -tool.
#
def breakBuild(newFindings):
    #Do we need to break the build
    if(logging.getLogger().isEnabledFor(logging.DEBUG)):
        logging.debug(f'--break_build={args.break_build} -> {"There was "}{len(newFindings)} new findings -> {"breaking the build..." if len(newFindings) > 0 else " will not break the build, because there was no new findings"}')
    if len(newFindings) > 0:
        raise SystemExit("Build break requested!")

#
# Will execute the real Coverity commit, if --dryrun=False, otherwise it will not do the commit.
#
def executeCoverityCommit():
    if not args.dryrun:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug("--dryrun=False -> will run the commit!")
        os.system(f'{args.coverity_home}cov-commit-defects --dir="{args.intermediate_dir}" --url="{args.coverity_url}" --user="{args.username}" --password="{args.password}" --stream="{args.stream_name}"')
    elif(logging.getLogger().isEnabledFor(logging.DEBUG)):
        logging.debug("--dryrun=True -> no commit done!")

#
# This method is sending the Teams notification only, if there are any new findings or emit percentage is too low.
# You need to give --teams_webhook_url with webhook url, otherwise it will not od the notification.
#
def sendTeamsNotification(newIssueMergeKeys, emitmessage):
    if args.teams_webhook_url:
        logging.info("Notification process started...")
        teamsMessage = pymsteams.connectorcard(args.teams_webhook_url)
        if newIssueMergeKeys and len(newIssueMergeKeys) > 0:
            teamsMessage.title(f'There are new findings in stream: {args.stream_name}')
            teamsMessage.summary("You have changes in stream")
            sec = pymsteams.cardsection()
            sec.title(f'There are {len(newIssueMergeKeys)} new findings')
            teamsMessage.addLinkButton( "View all project findings", args.coverity_url )
        else:
            teamsMessage.title(f'Emit percentage was too low for the stream: {args.stream_name}')
            teamsMessage.summary("Emit percentage was too low")
            sec = pymsteams.cardsection()
            sec.title(emitmessage)
        teamsMessage.addSection(sec)
        teamsMessage.summary("You have changes in stream")
        teamsMessage.send()
        logging.info("Notification sent!")
    else:
        if(logging.getLogger().isEnabledFor(logging.DEBUG)):
            logging.debug("No Teams notification sent, because teams webhook url not given! You can give it with --teams_webhook_url flag.")

def str2bool(v):
  return v.lower() in ("yes", "true", "t", "1")

#
# Main mathod
#
if __name__ == '__main__':
    start = timer()
    result = False
    parser = argparse.ArgumentParser(
        description="Coverity Commit Checker"
    )
    parser.register('type','bool',str2bool)
    #Parse commandline arguments
    parser.add_argument('--coverity_url', help="Coverity URL.", default="", required=True)
    parser.add_argument('--project_name', help="Coverity project name.", default="")
    parser.add_argument('--stream_name', help="Coverity stream name.", default="", required=True)
    parser.add_argument('--password', help='User password for Coverity', default="", required=True)
    parser.add_argument('--username', help='Username for Coverity', default="", required=True)
    parser.add_argument('--build_log_file', help='Path for Coverity build log file from folder where this script is running', default="build-log.txt")
    parser.add_argument('--check_emit', help='Is the emit percentage checked or not', default=True, type=str2bool)
    parser.add_argument('--dryrun', help='Is full commit wanted or not', default=False, type=str2bool)
    parser.add_argument('--break_build', help='Is breaking the build required', default=False, type=str2bool)
    parser.add_argument('--emit_threshold', help='Emit percentage threshold limit default=95', default=95, type=int)
    parser.add_argument('--viewID', help="ID of that view which result is used to get findings.", default="", required=False)
    # #Teams configs
    parser.add_argument("--teams_webhook_url", help="This is the url for your Teams Incoming WebHook.", default="")
    parser.add_argument('--log_level', help="Will print more info... default=INFO", default="DEBUG")
    # #Parameters for Coverity commit operation
    parser.add_argument('--intermediate_dir', help="Intermediate directory", default="idir")
    parser.add_argument('--coverity_home', help="Folder where coverity commandfiles are located. Example: /coverity/bin/", default="")
    parser.add_argument('--force_commit', help="Force commit, will skip all other checks", default=False, type=str2bool)
    
    args = parser.parse_args()
    #Initializing the logger
    logging.basicConfig(format='%(asctime)s:%(levelname)s:%(module)s: %(message)s', stream=sys.stderr, level=args.log_level)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    #Printing out the version number
    logging.info("CommitChecker version: " + __versionro__)
    fixedIssueMergeKeys,newIssueMergeKeys = [],[]
    if not args.force_commit:
        # Check first that is the emit percentage within given threshold, if not will exit.
        if args.check_emit:
            emitResult, emitmessage = checkEmitPrecentage()
            if not emitResult:
                sendTeamsNotification(None, emitmessage)
                raise SystemExit(f'Emit percentage was too low to continue, check the Coverity configuration: {emitmessage}')
            else:
                logging.info(f'The emit result was: {emitResult} -> {emitmessage}')
        # If project name is not given as a parameter, then it will try to get it with the given stream name.
        project_name = args.project_name if args.project_name else getProjectNameforStream()
        # If viewID is given as a param, then it will use given view to get the findings from Coverity Connect, otherwise it will get findings by the latest snapshotID
        if args.viewID:
            projectID = getProjectID(project_name)
            if projectID:
                fixedIssueMergeKeys,newIssueMergeKeys = checkFindings(getAnalysisMergeKeys(), getFindingsByView(projectID))    
        else:
            fixedIssueMergeKeys,newIssueMergeKeys = checkFindings(getAnalysisMergeKeys(), getFindingsBySnapshotID(getLatestComparableSnapshotIDByStream(args.stream_name), project_name))
        if len(fixedIssueMergeKeys) > 0: 
            if(logging.getLogger().isEnabledFor(logging.DEBUG)):
                logging.debug(f'Fixed finding mergeKeys are: {fixedIssueMergeKeys}')
            result = True
        if len(newIssueMergeKeys) > 0:
            if(logging.getLogger().isEnabledFor(logging.DEBUG)):
                logging.debug(f'New finding mergeKeys are: {newIssueMergeKeys}')
            result = True
        if result:
            sendTeamsNotification(newIssueMergeKeys, None)
            logging.info(f'{"--force_commit=True" if args.force_commit else "The finding check result was:"} {result} -> {"full commit needed" if result else "No need for full commit."}')
    # If there are any new or fixed findings or --force_commit=True, it will do the commit. If --dryrun is true, commit will not be done.
    if result or args.force_commit:
        executeCoverityCommit()
    if(logging.getLogger().isEnabledFor(logging.INFO)):
        end = timer()
        logging.info(f"Checking took: {end - start} seconds.")
    # If force_commit is False and break_build is True, it will break the build only if there are any NEW findings, otherwise there is no point to do it.
    if not args.force_commit and args.break_build: breakBuild(newIssueMergeKeys)
    logging.info(f'{"Commit done!" if result else "Commit was not needed at this time!"}')