from bento_mdf import MDFWriter
from bento_meta.model import Model
import argparse
import pandas as pd
from crdclib import crdclib
import requests
import json

from bento_meta.model import Node, Property, Term, Tag, Edge
from bento_mdf.validator import MDFValidator
from jsonschema import SchemaError, ValidationError
from yaml.parser import ParserError
from IPython.display import clear_output


def cleanHTML(inputstring):
    outputstring = inputstring.replace("<br>", "")
    return outputstring


def validateModel(filelist):
    try:
        MDFValidator(*filelist, raise_error=True).load_and_validate_schema()
    except SchemaError as e:
        clear_output()
        print(f"Schema error:\n{e}")


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



def mdfAddProperty(mdfmodel, node_prop_dict, add_node = False):
    """Adss property objects to an MDF model object.  If requested, missing nodes will be added

    :param mdfmodel: An MDF model object to which nodes will be added
    :type mdfmodel: MDF model object
    :param node_prop_dict: A dictionary with an individual node name as key and a list of dictionaries containing property information {nodename:[{propery_description}]}
    :type node_prop_dict: Dictionary
    :param property_description: A dicionary {prop:property_name, isreq: Yes or No indictating if property is required, 'val': The property data type or 'value_set' if Enums are to be added, 'desc': Property description}
    :type property_description: Dictionary
    :param add_node: If set to true, any nodes found in node_prop_dict that are not already in the model will be added.
    :type add_node:  Boolean, default is False
    :return: MDF Model with additional properties added
    :rtype: MDF Model object
    """

    for node, properties in node_prop_dict.items():
        #if add_node:
        #    if node not in list(mdfmodel.nodes):
        #        mdfmodel = mdfAddNodes(mdfmodel, [node])
        for prop_info in properties:
            if 'iskey' in prop_info:
                propobj =  Property({'handle': prop_info['prop'],
                                "_parent_handle": node,
                                'is_required': prop_info['isreq'],
                                'is_key': prop_info['iskey'],
                                'value_domain': prop_info['val'],
                                'desc': prop_info['desc']})
            else:
                propobj = Property({'handle': prop_info['prop'],
                                "_parent_handle": node,
                                'is_required': prop_info['isreq'],
                                'value_domain': prop_info['val'],
                                'desc': prop_info['desc']})
            nodeobj = mdfmodel.nodes[node]
            mdfmodel.add_prop(nodeobj, propobj)
    return mdfmodel




def addProps(datamodel, nodedict, add_node=False):
    node_prop_dict = {}
    edgelist = []
    taginfo = []
    for node, workign_df in nodedict.items():
        node_prop_dict[node] = []
        for index, row in workign_df.iterrows():
            valtype = 'String'
            req = 'No'
            if pd.notnull(row['Description']):
                description = crdclib.cleanString(str(row['Description']), True)
                description = cleanHTML(description)
            else:
                description = None
            if pd.notnull(row['Property']):
                tempinfo = {}
                propname = crdclib.cleanString(row['Property'], True)
                propname = cleanHTML(propname)
                print(f"Working on property {propname}")
                if "." in propname:
                    #print(f"This is a node.propery: {propname} for node {node}")
                    dstnode = propname.split(".")[0]
                    dstnode = dstnode.capitalize()
                    edgeinfo = {
                        'handle': f"of_{node}",
                        'desc': 'Obtained from node.property',
                        'mul': 'Unknown',
                        'ends':[{'src': node, 'dst': dstnode}]
                    }
                    edgelist.append(edgeinfo)
                else:
                    if pd.notnull(row['Required/optional']):
                        if row['Required/optional'] == 'R':
                            req = 'Yes'
                    tempinfo = {'prop': propname, "_parent_handle": node, 'isreq': req, 'val': valtype, 'desc': description}
                    #if "_id" in propname:
                    if propname.endswith("_id"):
                        print(f"{propname} is Key")
                        #tempinfo['Key'] = 'True'
                        #taginfo.append({'node':node, 'prop':propname, 'tag':{'key':'Key:', 'value': True}})
                        tempinfo['iskey'] = 'Yes'
                        print(tempinfo)
                    node_prop_dict[node].append(tempinfo)
    datamodel = mdfAddProperty(datamodel, node_prop_dict, False)
    #for tag in taginfo:
    #    crdclib.mdfAddTags(datamodel, 'property',(tag['node'],tag['prop']),tag['tag'])
    return datamodel, edgelist





def addTerms(datamodel, nodedict, verbose=0):
    # TODO: If there is no CDE, but a Permissible values column, add those as enums
    for nodename, working_df in nodedict.items():
        for index, row in working_df.iterrows():
            if 'CDE' in row:
                if pd.notnull(row['CDE']):
                    #cdeinfo = getCDEInfo(row['CDE'], verbose=verbose)
                    cdeinfo = crdclib.getCDEInfo(row['CDE'])
                    if cdeinfo['cdedef'] is not None:
                        cdedef = crdclib.cleanString(cdeinfo['cdedef'],True)
                        cdedef = cleanHTML(cdedef)
                    cdeid = str(row['CDE'])
                    # For some reason, IDs out of Excel are formated like a float
                    cdeid = cdeid.split(".")[0]
                    termvalues = {'handle': row['Property'], 'value': cdeinfo['cdename'], 'origin_version': cdeinfo['cdever'], 'origin_name':'caDSR', 'origin_id':cdeid, 'origin_definition': cdedef, 'nanoid': 'cdeurl'}
                    datamodel = crdclib.mdfAnnotateTerms(datamodel, nodename, row['Property'], termvalues)
                elif 'Permissible values' in row:
                    if pd.notnull(row['Permissible values']):
                      #print(f"Type: {type(row['Permissible values'])}\n{row['Permissible values']}")
                      pvlist = row['Permissible values'].split("\n")
                      #print(f"Length of pvlist: {len(pvlist)}")
                      datamodel = crdclib.mdfAddEnums(mdfmodel=datamodel, nodename=nodename, propname=row['Property'], enumlist=pvlist)
    return datamodel



def writeFiles(mdf, configs, verbose=0):
    # This writes out the separate mode, property, etc., if reuested in the config.
    jsonobj = json.dumps(MDFWriter(mdf).mdf)
    mdfdict = json.loads(jsonobj)

    if len(configs['mdffiles']) >= 1:
        for entry in configs['mdffiles']:
            for mdfsection, filename in entry.items():
                if mdfsection != 'Model':
                    if verbose >= 1:
                        print(f"Writing file {entry}")
                    printnode = {}
                    printnode[mdfsection] = mdfdict.pop(mdfsection, None)
                    crdclib.writeYAML(configs['workingpath']+filename, printnode)
    #After printing out the requested sections, print out what's left
    for entry in configs['mdffiles']:
        for mdfsection, filename in entry.items():
            if mdfsection == 'Model':
                crdclib.writeYAML(configs['workingpath']+filename, mdfdict)



def addEdges(datamodel, edgelist, verbose=0):
    if verbose >= 2:
        print(f"Starting Edge list:\n{edgelist}")
    listofedges = []
    for edge in edgelist:
        if verbose >= 2:
            print(f"Adding edge: {edge}")
        for end in edge['ends']:
            listofedges.append({'handle':edge['handle'], 'multiplicity':edge['mul'], 'src': end['src'], 'dst':end['dst'], 'desc': edge['desc']})
    if verbose >= 2:
        print(f"Complete set of edges to add:\n{listofedges}")
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
        if node not in configs['excludetabs']:
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
    idc_mdf, edgelist = addProps(idc_mdf, nodedict, False)

    # Add terms
    if args.verbose >= 1:
        print('Adding CDE Terms to model')
    idc_mdf = addTerms(idc_mdf, nodedict, args.verbose)

    #Add node tags
    if args.verbose >=1:
        print('Adding tags to nodes')
    if 'tags' in configs:
        idc_mdf = addTags(idc_mdf, configs['tags'], args.verbose )

    # Add edges if they are provided in the configs file
    if 'edges' in configs:
        if len(configs['edges']) >= 1:
            if args.verbose >= 1:
                print("Adding relationships to the model")
            for edge in configs['edges']:
                edgelist.append(edge)
            #idc_mdf = addEdges(idc_mdf, configs['edges'])
            idc_mdf = addEdges(idc_mdf, edgelist)
    elif len(edgelist) > 0:
        if args.verbose >= 1:
            print("Adding edges to model")
        idc_mdf = addEdges(idc_mdf, edgelist, args.verbose)



  #  # Model is done, validated before writing
  #  if args.verbose >= 1:
  #      print("Validating final model")
  #  validateModel(idc_mdf)

    # Write out the files
    if args.verbose >= 1:
        print(f"Writing out the MDF Files in {configs['workingpath']}")
    writeFiles(idc_mdf, configs, args.verbose)

    if args.verbose >= 1:
        print("Validating final model")
    filelist = []
    for fileentry in configs['mdffiles']:
        for filename in fileentry.values():
            filelist.append(f"{configs['workingpath']}{filename}")
    validateModel(filelist)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--configfile", required=True,  help="Configuration file containing all the input info")
    parser.add_argument('-v', '--verbose', action='count', default=0, help=("Verbosity: -v main section -vv subroutine messages -vvv data returned shown"))

    args = parser.parse_args()

    main(args)
