from bento_mdf import MDFWriter
from bento_meta.model import Model
import argparse
import pandas as pd
from crdclib import crdclib
import requests
import json




def cleanHTML(inputstring):
    outputstring = inputstring.replace("<br>", "")
    return outputstring


def getCDEInfo(cdeid, version=None, verbose=0):
    definition = None
    cdename = None
    cdeversion = None
    if version is None:
        url = "https://cadsrapi.cancer.gov/rad/NCIAPI/1.0/api/DataElement/"+str(cdeid)
    else:
        url = "https://cadsrapi.cancer.gov/rad/NCIAPI/1.0/api/DataElement/"+str(cdeid)+"?version="+str(version)
    headers = {'accept':'application/json'}

    if verbose >= 2:
        print(f"caDSR URL:\n{url}")
    try:
        results = requests.get(url, headers = headers)
    except requests.exceptions.HTTPError as e:
        print(e)
    if results.status_code == 200:
        results = json.loads(results.content.decode())
        if results['DataElement'] is not None:
            if verbose >= 3:
                print(f"Return caDSR JSON:\n{results['DataElement']}")
            if 'preferredName' in results['DataElement']:
                cdename = results['DataElement']['preferredName']
            else:
                cdename = results['DataElement']['longName']
            if 'preferredDefinition' in results['DataElement']:
                definition = results['DataElement']['preferredDefinition']
            else:
                definition = results['DataElement']['definition']
            cdeversion = results['DataElement']['version']
    else:
        cdename = 'caDSR Name Error'
    if definition is not None:
        definition = crdclib.cleanString(definition, True)
    return {'cdename':cdename, 'cdedef':definition, 'cdever':cdeversion}





def addProps(datamodel, nodedict, add_node=False):
    node_prop_dict = {}
    for node, workign_df in nodedict.items():
        node_prop_dict[node] = []
        for index, row in workign_df.iterrows():
            valtype = 'String'
            if pd.notnull(row['Description']):
                description = crdclib.cleanString(str(row['Description']), True)
                description = cleanHTML(description)
            else:
                description = None
            if pd.notnull(row['Property']):
                propname = crdclib.cleanString(row['Property'], True)
                propname = cleanHTML(propname)
            tempinfo = {'prop': propname, "_parent_handle": node, 'isreq': 'No', 'val': valtype, 'desc': description}
            node_prop_dict[node].append(tempinfo)
    datamodel = crdclib.mdfAddProperty(datamodel, node_prop_dict, False)
    return datamodel





def addTerms(datamodel, nodedict, verbose=0):
    for nodename, working_df in nodedict.items():
        for index, row in working_df.iterrows():
            if 'CDE' in row:
                if pd.notnull(row['CDE']):
                    cdeinfo = getCDEInfo(row['CDE'], verbose=verbose)
                    if cdeinfo['cdedef'] is not None:
                        cdedef = crdclib.cleanString(cdeinfo['cdedef'],True)
                        cdedef = cleanHTML(cdedef)
                    cdeid = str(row['CDE'])
                    # For some reason, IDs out of Excel are formated like a float
                    cdeid = cdeid.split(".")[0]
                    termvalues = {'handle': row['Property'], 'value': cdeinfo['cdename'], 'origin_version': cdeinfo['cdever'], 'origin_name':'caDSR', 'origin_id':cdeid, 'origin_definition': cdedef, 'nanoid': 'cdeurl'}
                    datamodel = crdclib.mdfAnnotateTerms(datamodel, nodename, row['Property'], termvalues)
    return datamodel



def writeFiles(mdf, configs, verbose=0):
    # This writes out the separate mode, property, etc., if reuested in the config.
    jsonobj = json.dumps(MDFWriter(mdf).mdf)
    mdfdict = json.loads(jsonobj)

    if len(configs['mdffiles']) >= 1:
        for entry in configs['mdffiles']:
            if verbose >= 1:
                print(f"Writing file {entry}")
            for mdfsection, filename in entry.items():
                printnode = {}
                printnode[mdfsection] = mdfdict.pop(mdfsection, None)
                crdclib.writeYAML(configs['workingpath']+filename, printnode)
    #After printing out the requested sections, print out what's left
    crdclib.writeYAML(configs['workingpath']+configs['mdffile'], mdfdict)





def addEdges(datamodel, edgelist):
    listofedges = []
    for edge in edgelist:
        for end in edge['ends']:
            listofedges.append({'handle':edge['handle'], 'multiplicity':edge['mul'], 'src': end['src'], 'dst':end['dst'], 'desc': edge['desc']})
    datamodel = crdclib.mdfAddEdges(datamodel, listofedges)
    return datamodel



def addTags(datamodel, taglist, verbose=0):
    for tag in taglist:
        for tagname, tagvalue in tag.items():
            datamodel = crdclib.mdfAddTags(datamodel, 'node', tag['node'], {'key':tagname, 'value':tagvalue})
    return datamodel



        

def main(args):
    # Setup
    if args.verbose >= 1:
        print("Config and dictionary setup")
    configs = crdclib.readYAML(args.configfile)
    nodedict = {}

    #Read the input file
    
    if args.verbose >= 1:
        print(f"Reading Excel file {configs['excelfile']}")
    xlfile = pd.ExcelFile(configs['workingpath']+configs['excelfile'])

    #Get the node names (sheet names)
    if args.verbose >= 1:
        print("Setting up node/dataframe dictionary")
    for node in xlfile.sheet_names:
        temp_df = pd.read_excel(configs['workingpath']+configs['excelfile'], node)
        nodedict[node] = temp_df
    
    # Create an empty model object
    if args.verbose >= 1:
        print("Setting up an empty model")
    idc_mdf = Model(handle= configs['handle'], version= configs['version'])

    # Add nodes
    if args.verbose >= 1:
        print('Adding nodes to the model')
    idc_mdf = crdclib.mdfAddNodes(idc_mdf, list(nodedict.keys()))
    
    # Add properties
    if args.verbose >= 1:
        print("Adding properties to the model")
    idc_mdf = addProps(idc_mdf, nodedict, False)

    # Add terms
    if args.verbose >= 1:
        print('Adding CDE Terms to model')
    idc_mdf = addTerms(idc_mdf, nodedict, args.verbose)

    #Add node tags
    if args.verbose >=1:
        print('Adding tags to nodes')
    idc_mdf = addTags(idc_mdf, configs['tags'], args.verbose )

    # Add edges if they are provided in the configs file
    if 'edges' in configs:
        if len(configs['edges']) >= 1:
            if args.verbose >= 1:
                print("Adding relationships to the model")
            idc_mdf = addEdges(idc_mdf, configs['edges'])

    # Write out the files
    if args.verbose >= 1:
        print(f"Writing out the MDF Files in {configs['workingpath']}")
    writeFiles(idc_mdf, configs, args.verbose)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--configfile", required=True,  help="Configuration file containing all the input info")
    parser.add_argument('-v', '--verbose', action='count', default=0, help=("Verbosity: -v main section -vv subroutine messages -vvv data returned shown"))

    args = parser.parse_args()

    main(args)
