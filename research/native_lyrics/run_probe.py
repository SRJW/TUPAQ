"""Separate parser processes; report acceptance/times, never claim iOS support."""
import json,math,subprocess,sys,tempfile
from pathlib import Path


def verdict(report,expected):
    if not report.get('parser_available'):return 'parser_unavailable'
    if report.get('status')=='unqualified-method-signature':return 'signature_unqualified'
    if expected is None:return 'negative_control_rejected' if not report.get('parsed') else 'negative_control_accepted'
    if not report.get('parsed') or report.get('error') or report.get('exception_class'):return 'parse_rejected'
    lines=report.get('lines',[])
    if not isinstance(lines,list) or len(lines)!=len(expected):return 'timing_mismatch'
    for line,pair in zip(lines,expected):
        for key,value in zip(('start','end'),pair):
            actual=line.get(key)
            if type(actual) not in (int,float) or not math.isfinite(actual) or abs(actual-value)>.001:return 'timing_mismatch'
    return 'synthetic_times_match'


def main():
    executable=Path(sys.argv[1]).resolve();inputs=json.loads(Path(sys.argv[2]).read_text());output=Path(sys.argv[3]);output.mkdir(exist_ok=True)
    summaries=[]
    for sample in inputs:
        with tempfile.TemporaryDirectory(prefix='native-lyrics-') as root:
            source=Path(root)/'input.json';target=Path(root)/'output.json'
            source.write_text(json.dumps({'xml':sample['xml']}),encoding='utf-8')
            try:
                process=subprocess.run([str(executable),str(source),str(target)],capture_output=True,timeout=30)
                if process.returncode or not target.is_file():report={'parser_available':False,'status':'process_failed','exit_code':process.returncode}
                else:report=json.loads(target.read_text())
            except subprocess.TimeoutExpired:report={'parser_available':False,'status':'process_timeout'}
            report['sample']=sample['name'];report['verdict']=verdict(report,sample['expected']);report['iphone_validation']=False
            (output/(sample['name']+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
            summary={key:report.get(key) for key in ('sample','verdict','status','os','framework_loaded','parser_available','parsed','info_type','lines','iphone_validation')}
            summaries.append(summary)
            print('::notice title=Native lyrics parser::'+json.dumps(summary,separators=(',',':')))
    (output/'summary.json').write_text(json.dumps(summaries,indent=2),encoding='utf-8')


if __name__=='__main__':main()
