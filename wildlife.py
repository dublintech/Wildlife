'''
Created on 1 Feb 2012

@author: Alex
'''
#-------------------------------------------------------------------------------
# name:        wildlife
# Purpose:     To analyse nightly builds for new failures. 
#
# Author:      Alex Staveley
#
# Created:     20/01/2012
#-------------------------------------------------------------------------------
#!/usr/bin/env python

## Major stumbling blocks doing this. 
## 1. Connecting to Jenkins. N/W problems
## 2. Problems with google spreadsheet API
## - list feed will not read blank rows. It think it is the end of the document.
## - cannot insert into the middle of a list feed
## - cannot insert into a spreadsheet with column names that have spaces or capital letters
## - google won't let you insert if top row is frozen.

## Improvement ideas: 
## -1: Get printing on the same line for 1,2,3,4,5
## 0. Refactor out global reference to args
## 1. Sort the defaultDict and get them to print nice. Might be an idea to use a defaultDict of dictionaries.
## This might be of help: http://docs.python.org/release/2.5.2/lib/defaultdict-examples.html
## 1.b Get help working
## 2. Code tidy up.  Put all methods which refer to old style at the end of script and rename the to include words old_style.
## 3. Add and remove to new spreadsheet
## 4. Pretify new spreasheet.  Put in "NEW FAILURE" for notes in new failures.
## 5. Update code to read failures from new style spreadsheet

# Rev 107.  Added wipeout detections
# Rev 108 - Changed default login
# Rev 109 - Rename to wildlife began refactoring args out.
# Rev 110 - general tidy up, addition of branch testing
# Rev 111 - Addition of configuration file.
# Rev 113 - Removal of mapping errors

from xml.etree import ElementTree as ET
import os
import argparse
import logging
import sys
import operator

from pprint import pformat
from datetime import datetime
from collections import defaultdict

# Imports for calling google spreadsheet...
import gdata.spreadsheet.service


# Logging stuff
LOGGING_LEVELS = {'critical': logging.CRITICAL,
                  'error': logging.ERROR,
                  'warning': logging.WARNING,
                  'info': logging.INFO,
                  'debug': logging.DEBUG}

def main(args):
    os.system('banner Wildlife') 
    set_up_logging(args.l);
    # Get the configuration data
    configData = parse_config_xml(args.f);
    projectmappings = configData['projectmappings']
    jobmappings = configData['jobmappings'];
    username = configData['username']
    password = configData['password']
    
    # Get all the builds from the configuration
    for k, v in jobmappings.items():
        # k is the name of build e.g. Build, Trunk
        # v is the spreadsheet to jenkins mapping for that build.
        os.system('banner ' + str(k))
        do_nightlies(args, v, k, projectmappings, username, password);
    
def setupArgs():
    parser=argparse.ArgumentParser(description='''This script reads junit test result files from Jenkins,\n
                                            and compares them to the latest results in the nightlies \n
                                            spreadsheet stored in google docs.''',
                                            epilog='''Enjoy this script and report any issues to Alex!''')
                                            
    parser.add_argument('-l', type=str, default='info', help='logging level. Default is info. Use debug if you have problems.')
    parser.add_argument('-d', type=str, default ='', help='datetime of build to analyse.  If none is specified, the latest is taken')
    parser.add_argument('-u', type=str, default='nightlies2012@gmail.com', help='User to login as e.g. alexstaveley@gmail.com')
    parser.add_argument('-p', type=str, default='thetasgroup', help='password for the user')
    parser.add_argument('-s', type=str, default='New Nightly Roundup Details', help='name of spreadsheetname to check and update')
    #parser.add_argument('-j', type=str, default='J:\jobs\\', help='Jenkins path')
    parser.add_argument('-j', type=str, default='C:\\jaketest\\java\\newenv\\jenkins\\jobs\\', help='Jenkins path')
    parser.add_argument('-n', type=int, default=1, help='The minimum number of jenkins junit test files to expect')
    parser.add_argument('-r', action='store_true', default=False, help='Updates spreadsheet')
    parser.add_argument('-x', action='store_true', default=True, help='Flag to stop if there is a wipeout')
    parser.add_argument('-o', type=str, default='Nightly Roundup Details', help='Old spreadsheet name')
    parser.add_argument('-f', type=str, default='config.xml', help='name of configuration XML file to use')
    args = parser.parse_args()
    return args;
    
def set_up_logging(userLoggingLevel):
    logging_level = LOGGING_LEVELS.get(userLoggingLevel, logging.INFO)
    log = logging.getLogger()
    ch = logging.StreamHandler()
    ch.setLevel(logging_level)
    log.setLevel(logging_level)
    log.addHandler(ch);

    # Now set up file.
    
    logfilename = datetime.now().strftime('wildlife_%H_%M_%a_%d_%b_%Y.log')

    fh = logging.FileHandler(logfilename)
    fh_fmt = logging.Formatter("%(levelname)s %(asctime)s %(process)d %(funcName)s(),%(lineno)d: %(message)s")
    fh.setFormatter(fh_fmt)
    fh.setLevel(logging.DEBUG)
    log.setLevel(logging.DEBUG)
    log.addHandler(fh);
    logging.info("@author Alex Stavliniski, Feb 2012")
    logging.info("Running nightlies tests comparison at " + datetime.now().strftime("%H:%M" + " %a %d %b %Y") + 
                    ", logfile is" + logfilename);


def do_nightlies(args, testGroupmappings, worksheetname, projectmappings, username, password):
    """ Runs python script, to lookat night builds, and update spreadsheet

        Note: For this script.  The spreadsheet must use specific names.

    """
    
    logging.debug(">>do_nightlies()");
    # 1. Get all test results from jenkins
    allTestResultsFromJenkins = parse_all_xmls_for_testresults(args.j, args.n, testGroupmappings, projectmappings);

    #2. Get passed tests from jenkins
    passedJenkinsTests = [testresult for testresult in allTestResultsFromJenkins if testresult['failedSince'] == '0']

    #3. Get the failed tests from jenkins
    failedJenkinsTests = [testresult for testresult in allTestResultsFromJenkins if testresult['failedSince'] != '0']
    logging.info("#tests ran in Jenkins=" + str(len(allTestResultsFromJenkins)) +
            ",#success=" + str(len(passedJenkinsTests))  + ", #failures=" + str(len(failedJenkinsTests)) +
            ", check logfile for further info")
    # log the failures
    logging.debug("Failed tests in Jenkins: \n" + pformat(failedJenkinsTests))

    # Now the google client stuff!
    # Get the google client
    gd_client = get_gd_client(username, password);
    
    #4. Get the failed tests from previous build.

    failureFromspreadsheet = get_failures_from_nb_spreadsheet(gd_client, args.s, worksheetname);
    logging.debug("Failures from spreadsheet are: \n" + pformat(failureFromspreadsheet));

    # 5. Now determine what failures are no longer failing
    fixedFailures = get_failures_that_are_fixed(failureFromspreadsheet, passedJenkinsTests, testGroupmappings, projectmappings);
    logging.info("Of the " + str(len(failureFromspreadsheet)) + " failures that were previously reported, " \
             + str(len(fixedFailures)) + " are now fixed!");

    # Now determine new failures
    newFailures = get_new_failures(failedJenkinsTests, failureFromspreadsheet, testGroupmappings, projectmappings);
    log_project_failure_summary(failedJenkinsTests, newFailures)
    
    if len(newFailures) > 500:
        logging.info("WIPEOUT ALERT - that's way too many errors!!!");
        # Has exit on wipe being set?
        if args.x:                    
            sys.exit(["Sorry way too many errors. Your build is a mess. Take a look at yourself in the mirror!"]);
    
    os.system('banner Wildlife Analysis:') 
    
    if len(fixedFailures) > 0:
        logging.info("Remove these %d dudes from the spreadsheet:" % len(fixedFailures))
        # print summary advise.
        sortedFixedFailures = sorted(fixedFailures, key=lambda k:(k['testgrouping'], k['project'], k['testsuite'], k['test']))
        for i, fixedFailure in enumerate(sortedFixedFailures):
            # output testGrouping, project, Test Suite, Test, row
            logging.info(str(i + 1) + ":Row=" + str(fixedFailure['row']) + ", testgrouping=" +  fixedFailure['testgrouping'] + ", " + \
                        "project=" + fixedFailure['project'] + ", " + \
                        "testsuite=" + fixedFailure['testsuite'] + ", " + \
                        "test=" + fixedFailure['test']);
    else:
        logging.info("Hmm... There are no fixed failures...");
    if len(newFailures) > 0:
        logging.info("I also advice you to add the following %d failures to the spreadsheet:" % len(newFailures))
        sortedNewFailures = sorted(newFailures, key=lambda k:(k['testgrouping'], k['project'], k['testsuite'], k['test']))
        for i, newFailure in enumerate(sortedNewFailures):
            # output testGrouping, project, Test Suite, Test, row
            logging.info(str(i + 1) + ": " + newFailure['testgrouping'] + "," + \
                        "prj=" + newFailure['project'] + ", " + \
                        "suite=" + newFailure['testsuite'] + ", " + \
                        "test=" + newFailure['test']);
    else:
        logging.info("Good news! There are no new failures!");

    # Now delete fixed failures and add new failures.
    if args.r:
        delete_fixed_tests_from_spreasheet(gd_client, fixedFailures, args.s, worksheetname);
        # reverse group mappings.
        reversemappings = dict((v,k) for k,v in testGroupmappings.items())
        reverseprojectmappings = dict((v,k) for k,v in projectmappings.items())
        add_new_failures_to_spreasheet(gd_client, newFailures, args.s, worksheetname, reversemappings, reverseprojectmappings);
    logging.debug("<<do_nightlies()");

def log_project_failure_summary(allfailures, newFailures):
    logging.info("Of the " + str(len(allfailures)) + " failures in the latest build, " \
             + str(len(newFailures)) + " are new failures!");
    testGroupprojectFailures = defaultdict(int)
    for failure in allfailures:
        testGroupprojectFailures[failure["testgrouping"] + " " + failure["project"]] +=1
    # Reverse to make it easier to read we want to see the biggest failures first.
    sortedGroupprojectFailures = sorted(testGroupprojectFailures.iteritems(), key=operator.itemgetter(1), reverse=True)
   
    # log
    logging.info("Total failure summary info:")
    
    for failure in sortedGroupprojectFailures:
        logging.info(str(failure[0]) + " has " + str(failure[1]) + " failures");
        
    newTestGroupprojectFailures = defaultdict(int)
    for newFailure in newFailures:
        newTestGroupprojectFailures[newFailure["testgrouping"] + " " + newFailure["project"]] +=1
        
    # Reverse to make it easier to read we want to see the biggest failures first
    sortedNewTestGroupprojectFailures = sorted(newTestGroupprojectFailures.iteritems(), key=operator.itemgetter(1), reverse=True);
   
    logging.info("New failure summary info:")
    for summaryFailureInfo in sortedNewTestGroupprojectFailures:
        logging.info(str(summaryFailureInfo[0]) + " has " + str(summaryFailureInfo[1]) + " new failures");

def parse_all_xmls_for_testresults(jenkinshome, minNumberFiles, testGroupmappings, projectmappings, date = ""):
    """
    Reads all XML junit test result files generated by JENKINS.

    This will return a dictionary where each element is of the form:

    """
    #1 Get files to read.
    filepaths = get_files_to_read(jenkinshome, minNumberFiles, testGroupmappings, projectmappings, date);
    #2 Read files and extract test results.
    testresultsList = [];
    # Loop thru all files.
    numberOfFilesToParse = len(filepaths);
    logging.debug("Starting the parsing of "+ str(numberOfFilesToParse) + " files...");
    for i in range(len(filepaths)):
        filepathdictionary = filepaths[i];
        filepathvalue = filepathdictionary['filepath']
        logging.info(str(numberOfFilesToParse - i) + " file left to parse");
        logging.debug("\nBegin parsing file " + filepathvalue);
        file_cases_dict = parse_xml(filepathdictionary['testgrouping'], \
                                filepathdictionary['project'], filepathvalue);
        # Join tip fromstack over flow
        # http://stackoverflow.com/questions/38987/how-can-i-merge-two-python-dictionaries-as-a-single-expression
        testresultsList.extend(file_cases_dict);
    logging.info("Finished parsing all Jenkins' junit xml files.")
    return testresultsList;

def get_files_to_read(jenkinspath, minNumberFiles, testGroupmappings, projectmappings, date = ""):
    """
    Gets the file paths for junit test result file that will eventually be parsed.

    Will return list of dictionaries, where each dictionary is of the form:
        testGrouping:
        project:
        filepath:
    """
    logging.debug(">>get_files_to_read()");
    # filepaths is a dictionary key will be the file key,
    # value will be the file path.
    filepaths = [];
    basepath = jenkinspath +"{0}\\modules\\{1}\\builds\\";
    fullpath = basepath + "{2}\\junitResult.xml"
    logging.debug("basepath=" + basepath + ",fullpath=" + fullpath);
    
	#Iterate over the Jenkins projects - these are the values in dictionary SP_JK_TEST_GROUPINGS
    for testGrouping in testGroupmappings.values():
        # Iterate over the Jenkins projects - these are the values in dictionary project mappings
        for project in projectmappings.values():
		    # get date. Start with a filepath with a date to determine it.
            filepathNoDate = basepath.format(testGrouping, project);
            if os.path.exists(filepathNoDate):
                listoffiles = os.listdir(filepathNoDate)
                # Ensure list is not empty. An empty list is false uin python.
                if listoffiles:
                    try: 
                        date = max(listoffiles);
                        logging.debug("Checking the Jenkins' junit files from the datetime " + date + " got from filepath:" + filepathNoDate);
                    except: 
                        # We catch the exception just to make it easier to find quirks with directories etc.
                        logging.error("******  CAN'T GET datatime from " + str(listoffiles) + ", for file path=" + filepathNoDate);
                else:
                    # list is empty
                    logging.debug("Not even a datetime for : " + filepathNoDate);
                    # reset date
                    date = ""
                    logging.debug('** Won\'t parse:' + filepathNoDate)
                    continue;
            else: 
                logging.warn('**Won\'t parse:'  +  filepathNoDate + ' as it does not exist, can\'t get date');
                continue;
            filepath = fullpath.format(testGrouping, project, date)
            if os.path.exists(filepath):
                logging.debug('* Will parse:' + filepath)
                filepaths.append({'testgrouping':testGrouping, 'project':project,'filepath':filepath})
            else:
			    logging.debug('**Won\'t parse:' +  filepath + ' as filepath does not exist.');
    logging.info("Parsing " + str(len(filepaths)) + " logfiles");
    ### There should be certain number of jenkins files to parse otherwise the build probably 
    ### hasn't finished and there's no point running script.  This amount defaults to 28
    ### but can be set at command lin2  
    if len(filepaths) < minNumberFiles:
        logging.error("There should be at least " + str(minNumberFiles) + " jenkins test junit files to parse and check." + 
                       "Otherwise what's the point?  Please check your configuration");
        sys.exit(["No point reporting when there is not enough Jenkins test files build is probably not finished There"]);

    logging.debug("<<get_files_to_read(), files to read=" + pformat(filepaths))
    return filepaths;

def parse_xml(testgrouping, project, filepath):
    # Read the file as indicated by filepath.
    cases_list = [];
    root = ET.parse(filepath).getroot();
    for element in root.findall(".//cases/case"):
        classname = element.find('className').text;
        testname = element.find('testName').text;
        duration = element.find('duration').text;
        skipped = element.find('skipped').text;
        failedSince = element.find('failedSince').text;
        failure = 'n/a'  # defaults to not applicable
        if failedSince != '0': 
            failure = element.find('errorStackTrace').text;
        cases_dict = {'testgrouping':testgrouping, 'project': project, \
                'testsuite':classname, 'test':testname, 'skipped':skipped, \
                'failedSince':failedSince, 'duration':duration, 'failure': failure};
        cases_list.append(cases_dict);
    logging.debug("Finished parsing XML=" + filepath + ", number of test case entries=" + str(len(cases_list)));
    return cases_list;


def parse_config_xml(configfile="config.xml"):
    logging.info("Parsing configuration...")
    # Read the file as indicated by filepath.
    if not os.path.exists(configfile):
        logging.error("Filepath %s does not exist" % configfile)
        exit
    root = ET.parse(configfile).getroot()
    configdata = {}
    # Get user name and password
    # XML is like
    # <googlecredentials>
    #    <name>nightlies2012@gmail.com</name>
    #    <password>thetasgroup]</password>
    # </googlecredentials>
    username = root.find(".//googlecredentials/name")
    password = root.find(".//googlecredentials/password")

    configdata['username'] = username.text
    configdata['password'] = password.text
        
    # Get all builds jobs mappings
    builds = root.findall(".//build/name");
    jobmappings = {}
    for build in builds:
        buildmappings = {}
        for element in root.findall(".//build[name='" + build.text + "']" + "/jobs/mapping"):
            jenkinsname = element.find('jenkinsname').text;
            spreadsheetname = element.find('spreadsheetname').text;
            buildmappings[spreadsheetname] = jenkinsname
        jobmappings[build.text] = buildmappings;
        
    configdata['jobmappings'] = jobmappings;
        
    # Get project mappings
    projectmappings = {}
    for element in root.findall(".//projects/project"):
        jenkinsname = element.find('jenkinsname').text;
        spreadsheetname = element.find('spreadsheetname').text;
        projectmappings[spreadsheetname] = jenkinsname

    configdata['projectmappings'] = projectmappings; 
    return configdata;

def get_failures_from_nb_spreadsheet(gd_client, spreadsheetname, worksheetname):
    logging.info("Now getting failures from the spreadsheetname:" +
            spreadsheetname + ", worksheet="+ worksheetname);
    spreadsheetKey = get_nb_spreadsheet_key(gd_client, spreadsheetname);
    workSheetKey = get_worksheet_key(gd_client, spreadsheetKey, worksheetname);

    # Now look at the worksheets.
    allFailures = get_failures_from_new_style_worksheet(gd_client, spreadsheetKey, workSheetKey);
    return allFailures;    

def get_gd_client(useremail, password):
    """
    Gets a GD Client for Breako and logs him in.
    """
    gd_client = gdata.spreadsheet.service.SpreadsheetsService()
    gd_client.email = useremail
    if password is None or password == "":
        logging.error("No password specified.  Please specify password or it is impossible to connect to google docs")
        exit();
    gd_client.password = password
    gd_client.source = 'DublinTech_ConnectToGooglespreadsheet'
    logging.info("logging in user:" + gd_client.email)
    gd_client.ProgrammaticLogin()
    return gd_client;

def get_nb_spreadsheet_key(gd_client, spreadsheetname):
    """
    Gets spreadsheet key for Nightlybuilds.

    This is done by makes a REST call to get spreadsheet feed.
    And then checking the spreadsheets in feed for the nightly build
    spreadsheet.When that is found, the key for it is returned.
    """
    # If no key is specified, the google API GetspreadsheetsFeed will
    # return a spreadsheetsFeed.  If a key is specified,
    # a spreadsheetname will be returned.
    # See Doc: http://gdata-python-client.googlecode.com/hg/pydocs/gdata.spreadsheetname.service.html#spreadsheetnamesService for more information
    sheetsfeed = gd_client.GetSpreadsheetsFeed()
    # Now enumerate over and get the spread sheet we want.
    for i, entry in enumerate(sheetsfeed.entry):
        logging.debug('Iterating over spread sheets; + %s %s\n' % (i, entry.title.text))
        if entry.title.text == spreadsheetname:
            logging.debug(entry.id.text.rsplit('/', 1)[1])
            toReturn = entry.id.text.rsplit('/', 1)[1]
            logging.debug("spreadsheetnamekey=" + toReturn)
            return toReturn
    # should never get here
    sys.exit("Cannot get spreadsheetname key for " + spreadsheetname + ", check your configuration"); 
    

def get_worksheet_key(gd_client, spreadsheetKey, worksheetname):
    logging.debug(">> get_worksheet_key(spreadsheetKey=" + str(spreadsheetKey) + ", worksheetname=" + worksheetname)
    worksheetfeed = gd_client.GetWorksheetsFeed(spreadsheetKey)
    for i, entry in enumerate(worksheetfeed.entry):
        if worksheetfeed.entry[i].title.text == worksheetname:
            worksheetId = worksheetfeed.entry[i].id.text.rsplit('/', 1)[1]
            logging.debug("<< return, worksheetId= " + worksheetId)
            return worksheetId;
    # should never get here
    sys.exit("Cannot get worksheet key for " + worksheetname + ", check your configuration"); 
        
def get_worksheet(gd_client, spreadsheetKey, worksheetname):
    """Gets the worksheet for a specified gd_client, spreadsheetkey and worksheetname"""
    logging.debug(">> get_worksheet(spreadsheetKey=" + spreadsheetKey + ", worksheetname=" + worksheetname)
    worksheetfeed = gd_client.GetWorksheetsFeed(spreadsheetKey)
    for i, entry in enumerate(worksheetfeed.entry):
        if worksheetfeed.entry[i].title.text == worksheetname:
            return entry;

def get_failures_from_new_style_worksheet(gd_client, spreadsheetKey, workSheetKey):
    """
    Gets tests from a new style worksheet where columns are of the form:
        TestGrouping, project, TestSuite, Test, Failure, Responsible, Notes 
    """
    logging.debug(">>get_failures_from_new_style_worksheet(spkey=" + spreadsheetKey + ",work_id=" + workSheetKey);
    logging.info("Processing spreadsheet cells...")
    listfeed = gd_client.GetListFeed(spreadsheetKey, workSheetKey)
    
    alltestDetailsAsList = []
    #Alex to do optimise this using list comprehensions
    for i, entry in enumerate(listfeed.entry):
        spFailure = {}
        spFailure['testgrouping'] = entry.custom['testgrouping'].text
        spFailure['project'] = entry.custom['project'].text
        spFailure['testsuite'] = entry.custom['testsuite'].text
        spFailure['test'] = entry.custom['test'].text
        spFailure['failure'] = entry.custom['failure'].text
        spFailure['notes'] = entry.custom['notes'].text
        spFailure['row'] = i + 2  # Note we offset two: one for the spreadsheet title and one becauase feed starts at 0 not 1.
        alltestDetailsAsList.append(spFailure);
    logging.debug("<<get_failures_from_worksheet(), return=" + str(alltestDetailsAsList))
    return alltestDetailsAsList;
    
    
def get_failures_that_are_fixed(spreadsheetFailures, jenkinsPasses, testGroupmappings, projectmappings):
    """ Gets failures that were failing and are now fixed.

    """
    fixed_failures = []
    unresolvable_failures = []
    for spreadsheetFailure in spreadsheetFailures:
        for jenkinsTestPass in jenkinsPasses:
            try:
                shGroupingmapping = testGroupmappings[spreadsheetFailure['testgrouping']]
                shFailuremapping = projectmappings[spreadsheetFailure['project']]
                if  shGroupingmapping == jenkinsTestPass['testgrouping'] and \
                    shFailuremapping == jenkinsTestPass['project'] and \
                    spreadsheetFailure['testsuite'] == jenkinsTestPass['testsuite'] and \
                    spreadsheetFailure['test'] == jenkinsTestPass['test']:
                        # It's passed wow!
                        fixed_failures.append(spreadsheetFailure)
                        logging.info("Failure: " + spreadsheetFailure['testgrouping'] + ","  \
                             + spreadsheetFailure['project'] + "," + \
                            spreadsheetFailure['testsuite'] + "," + spreadsheetFailure['test'] + " is now passing!");
                        break
            except:
                logging.debug("Unexpected error:" + str(sys.exc_info()[0]) + "," + str(sys.exc_info()[1]) + \
                    "sF=" + str(spreadsheetFailure) + ",jTP=" + str(jenkinsTestPass));
                unresolvable_failures.append(spreadsheetFailure);
                break;
    if unresolvable_failures:
        logging.error("The following failures in the google spreadsheet cannot be compared as they have missing information:" + str(unresolvable_failures));
        sys.exit("Bombing out! There are: " + str(len(unresolvable_failures)) + " unresolvable errors"); 
    return fixed_failures


def get_new_failures(jenkinsFailures, spreadsheetFailures, testGroupmappings, projectmappings):
    new_failures = []
    unresolvable_failures = []
    for jenkinsFailure in jenkinsFailures:
        for spreadsheetFailure in spreadsheetFailures:
            try:
                shGroupingmapping = testGroupmappings[spreadsheetFailure['testgrouping']]
                shFailuremapping = projectmappings[spreadsheetFailure['project']]
                if  jenkinsFailure['testgrouping'] == shGroupingmapping and \
                    jenkinsFailure['project'] == shFailuremapping and \
                    jenkinsFailure['testsuite'] == spreadsheetFailure['testsuite'] and \
                    jenkinsFailure['test'] == spreadsheetFailure['test']:
                    # if it is not a new failure forget about it.
                    logging.debug("Failure: " + jenkinsFailure['testgrouping'] + ","  \
                         + jenkinsFailure['project'] + "," + \
                         jenkinsFailure['testsuite'] + "," + jenkinsFailure['test'] + " is not new");
                    break; # break the spreadsheetfailures, failure is not new.
            except:
                logging.error("Could not compare jenkins failure. " + \
                    "exc[0]" + sys.exc_info()[0] + ", exc[1]"+ sys.exc_info()[1] +", shFailuremapping=" + shFailuremapping + ", " + str(jenkinsFailure) + ", with spreadsheetfailure=" + str(spreadsheetFailure));
                unresolvable_failures.append(spreadsheetFailure);
                break;
        else:
            logging.debug("New failure: " + jenkinsFailure['testgrouping'] + ","  \
               + jenkinsFailure['project'] + "," + jenkinsFailure['testsuite'] + \
               "," + jenkinsFailure['test'] );
            new_failures.append(jenkinsFailure);
    # Do we have any unresolvable failures 
    if unresolvable_failures:
        logging.error("Unresolvable failures please check your spreadsheet. These are unresolvable:" + unresolvable_failures);
        sys.exit("Bombing out! There are: " + len(unresolvable_failures) + " unresolvable errors"); 
        # We have unresolvable.
        # Bomb out.
    return new_failures;

def delete_fixed_tests_from_spreasheet(gd_client, fixedFailures, spreadsheetname, worksheetname):
    """ Deletes rows from the spreadsheet that are fixed

        Remember in alist feed, the first row corresponds to table headers and google starts a list at the zero element.
        This means, that a spreadsheet which has 54 rows in appearance will have its last row at position 52 in 
        the list feed!
    """
    logging.debug(">> delete_fixed_tests_from_spreasheet()")
    # Step 1 sort so that it highest row number is first.
    sortedFixedFailures = sorted(fixedFailures, key=lambda k:( k['row']), reverse=True)
    logging.debug("Rows to be removed: \n" + pformat(sortedFixedFailures))
    
    # Step 2 Delete the rows.
    #feed = gd_client.GetListFeed(spkey, work_id)
   
    spreadsheetKey = get_nb_spreadsheet_key(gd_client, spreadsheetname);
    workSheetKey = get_worksheet_key(gd_client, spreadsheetKey, worksheetname);
    
    feed = gd_client.GetListFeed(spreadsheetKey, workSheetKey)
        
    for fixedFailure in sortedFixedFailures:    
        rowToDelete = int(fixedFailure['row']);
        logging.info("deleting from tg=" + fixedFailure['testgrouping'] + 
                     ",project=" + fixedFailure['project'] + ",testsuite=" + fixedFailure['testsuite'] +
                     ",test=" + fixedFailure['test'] +  ", at row=" + str(fixedFailure['row']));
                     # Note offest!  1  in delete one is because google does not count the first row.
                     # the other one is because google starts at 0. 
                     # hence 2 offset!
        response = gd_client.DeleteRow(feed.entry[rowToDelete - 2])  
        print("Response from delete is" + str(response));

def add_new_failures_to_spreasheet(gd_client, newFailures, spreadsheetname, worksheetname, jkToTestGroupings, reverseProjectmappings):    
    # We need to reverse the dictionary

    spreadsheetKey = get_nb_spreadsheet_key(gd_client, spreadsheetname);
    workSheetKey = get_worksheet_key(gd_client, spreadsheetKey, worksheetname);
    
    # Insert failures. 
    timenow = datetime.now().strftime('%H_%M_%a_%d_%b_%Y')
    for newFailure in newFailures:
        newFailureStr = "";
        if 'failure' in newFailure:
            newFailureFullStr = str(newFailure['failure'])
            newFailureStr = newFailureFullStr[0:75];
        else:
            newFailureStr = "";
        mappedFailure = {'project': reverseProjectmappings[newFailure['project']], 'testgrouping':jkToTestGroupings[newFailure['testgrouping']], 
                                'testsuite': newFailure['testsuite'], 
                                'test':newFailure['test'], 'failure': newFailureStr, 
                                'responsible': 'Unassigned', 'notes': 'New Failure ' + timenow}
        logging.info("Adding failure " + str(mappedFailure) + "to spreadsheet");
        # add toworksheet.
        entry = gd_client.InsertRow(mappedFailure, spreadsheetKey, workSheetKey)
    
        
if __name__ == "__main__":
    #main
    args = setupArgs()
    main(args)