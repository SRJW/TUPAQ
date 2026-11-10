"""Only synthetic words/times; no music, user files, credentials or URLs."""
import json,sys
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.lyrics_trial import ttml_from_lrc,NS,ITUNES


def cases():
    profile,_=ttml_from_lrc('[00:01.00] Alpha\n[00:03.00] Beta\n[00:05.00]',6000)
    expected=[[1.,3.],[3.,5.]]
    result=[{'name':'line_clock_v3','xml':profile,'expected':expected}]
    generic=ET.fromstring(profile)
    generic.attrib.pop('{'+ITUNES+'}timing');generic.attrib.pop('{http://www.w3.org/XML/1998/namespace}space')
    generic.remove(generic.find('{'+NS+'}head'))
    for p in generic.findall('.//{'+NS+'}p'):p.attrib.pop('{'+ITUNES+'}key');p.tail=None
    result.append({'name':'generic_clock_v1','xml':ET.tostring(generic,encoding='unicode'),'expected':expected})
    seconds=ET.fromstring(profile)
    for node in seconds.iter():
        for key in ('begin','end','dur'):
            if key in node.attrib:
                h,m,s=node.attrib[key].split(':');node.attrib[key]=f'{int(h)*3600+int(m)*60+float(s):.3f}s'
    result.append({'name':'line_seconds','xml':ET.tostring(seconds,encoding='unicode'),'expected':expected})
    word=ET.fromstring(profile);word.attrib['{'+ITUNES+'}timing']='Word'
    for p in word.findall('.//{'+NS+'}p'):
        text=p.text;p.text=None
        ET.SubElement(p,'{'+NS+'}span',{'begin':p.attrib['begin'],'end':p.attrib['end']}).text=text
    result.append({'name':'word_clock_synthetic','xml':ET.tostring(word,encoding='unicode'),'expected':expected})
    result.append({'name':'malformed_control','xml':'<tt><body><p>','expected':None})
    return result


if __name__=='__main__':Path(sys.argv[1]).write_text(json.dumps(cases()),encoding='utf-8')
