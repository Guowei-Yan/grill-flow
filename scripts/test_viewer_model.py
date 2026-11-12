import shutil
import subprocess
import unittest
from pathlib import Path

class TestViewerModel(unittest.TestCase):
    def _run_node(self, script: str) -> None:
        if not shutil.which("node"):
            self.skipTest("node required")
        model = Path(__file__).resolve().parent.parent / "viewer" / "model.js"
        wrapped = (
            "const assert = require('assert');"
            + "const fs = require('fs');"
            + "const vm = require('vm');"
            + "const ctx = {globalThis: {}, console, assert};"
            + "vm.createContext(ctx);"
            + "vm.runInContext(fs.readFileSync(process.argv[1],'utf8'), ctx);"
            + "vm.runInContext('const M = globalThis.GrillFlowModel;' + process.argv[2], ctx);"
        )
        r = subprocess.run(
            ["node", "-e", wrapped, str(model), script],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_fingerprint_and_initial_hop(self):
        self._run_node(
            "assert.strictEqual(M.fingerprint([' a ','b']), 'a\\nb');"
            "assert.strictEqual(M.initialUserHop({gate:{N:3}}), 3);"
            "assert.strictEqual(M.initialUserHop({gate:null}), 2);"
            "assert.strictEqual(M.changeMarker('added'), '+');"
            "assert.strictEqual(M.changeMarker('deleted'), '\\u2212');"
            "assert.strictEqual(M.changeMarker('present'), '\\u00b7');"
            "assert.strictEqual(M.changeMarker(null), '?');"
            "assert.strictEqual(M.edgeColor('import'), '#6c8cff');"
            "assert.strictEqual(M.defaultTab('all-structural', 1), 'Structural');"
            "assert.strictEqual(M.defaultTab('only-delete', 0), 'Structural');"
            "assert.strictEqual(M.defaultTab('only-delete', 2), 'Flows');"
            "assert.strictEqual(M.effectiveHop(2, null), 2);"
            "assert.strictEqual(M.effectiveHop(2, 5), 5);"
            "assert.strictEqual(M.effectiveHop(4, 1), 4);"
            "assert.strictEqual(M.stickyHeaderFields('k',{path:'a.ts',hop:null}).hopLabel,'\\u2014');"
            "assert.strictEqual(M.changeFilterMatch('deleted','deleted','git-diff'), true);"
            "assert.strictEqual(M.changeFilterMatch('present','deleted','git-diff'), false);"
            "const vw=M.virtualWindow(0,88,10);"
            "assert.strictEqual(vw.start,0);"
            "assert.strictEqual(vw.end, Math.min(10, 0 + Math.ceil(88/44) + 10));"
            "const hrs=[{phase:'graph',kind:'g',obligationId:'x'},{phase:'x',kind:'n',obligationId:'o'},"
            + "{phase:'y',kind:'m'}];"
            "const rl=M.runLevelHardRejects(hrs);"
            "assert.strictEqual(rl.length,2);"
            "assert.ok(rl.some(h=>h.kind==='g') && rl.some(h=>h.kind==='m'));"
        )

    def test_selection_file_not_consumer_join(self):
        self._run_node(
            "const obs=[{obligationId:'o1',path:'a.ts',line:1,change:'added',kind:'semantic'},"
            + "{obligationId:'o2',path:'b.ts',line:2,change:'present',kind:'semantic'},"
            + "{obligationId:'o3',path:'a.ts',line:3,change:'deleted',kind:'semantic'}];"
            + "const led={o1:{state:'covered',disposition:{kind:'semantic',logic:['L'],"
            + "inputs:[],outputs:[],consumers:['sym:x']}},"
            + "o2:{state:'waived',disposition:null},"
            + "o3:{state:'uncovered',disposition:null}};"
            + "const by=Object.fromEntries(obs.map(o=>[o.obligationId,o]));"
            + "const fileIds=M.selectionObligationIds('file:a',{kind:'file',path:'a.ts'},obs,led);"
            + "assert.deepStrictEqual(fileIds,['o1','o3']);"
            + "const symIds=M.selectionObligationIds('sym:x',{kind:'symbol',qualname:'X'},obs,led);"
            + "assert.deepStrictEqual(symIds,['o1']);"
            + "const agg=M.headerAggregates(['o1','o2','o3'],by,led);"
            + "assert.strictEqual(agg.added,1);"
            + "assert.strictEqual(agg.deleted,1);"
            + "assert.strictEqual(agg.uncovered,1);"
            + "assert.strictEqual(agg.flows,1);"
            + "assert.strictEqual(agg.structural,0);"
            + "const fragLed={}; const fragObs=[];"
            + "for(let i=0;i<10;i++){const id='file:big.py:'+i+':x';"
            + "fragObs.push({obligationId:id,path:'big.py',line:i});"
            + "fragLed[id]={state:'covered',disposition:{kind:'semantic',logic:['only-'+i]}}}"
            + "const frag=M.semanticFlowStats(fragLed,fragObs);"
            + "assert.ok(frag.violatingPaths.indexOf('big.py')>=0);"
            + "const goodLed={}; const goodObs=[];"
            + "for(let i=0;i<10;i++){const id='file:ok.py:'+i+':y';"
            + "goodObs.push({obligationId:id,path:'ok.py',line:i});"
            + "goodLed[id]={state:'covered',disposition:{kind:'semantic',logic:['shared']}}}"
            + "assert.deepStrictEqual(M.semanticFlowStats(goodLed,goodObs).violatingPaths,[]);"
            + "const tinyLed={}; const tinyObs=[];"
            + "for(let i=0;i<3;i++){const id='file:t.py:'+i+':z';"
            + "tinyObs.push({obligationId:id,path:'t.py',line:i});"
            + "tinyLed[id]={state:'covered',disposition:{kind:'semantic',logic:['u'+i]}}}"
            + "assert.deepStrictEqual(M.semanticFlowStats(tinyLed,tinyObs).violatingPaths,[]);"
        )

    def test_flow_prose_groups_search_layout(self):
        self._run_node(
            "const d={kind:'semantic',logic:['A','B'],inputs:['i'],outputs:['o'],"
            + "consumers:['c',{label:'z'}],preChangeRole:'p',removalImpact:'r',change:'deleted'};"
            + "const prose=M.flowProse(d);"
            + "assert.ok(prose.includes('Logic: A; B'));"
            + "assert.ok(prose.includes('In: i'));"
            + "assert.ok(prose.includes('Out: o'));"
            + "assert.ok(prose.includes('Consumers: c, unknown:z'));"
            + "assert.ok(prose.includes('Pre: p'));"
            + "assert.ok(prose.includes('Impact: r'));"
            + "const sec=M.flowProseSections(d);"
            + "assert.deepStrictEqual(sec.logic,['A','B']);"
            + "assert.deepStrictEqual(sec.consumers,['c','unknown:z']);"
            + "const runs=M.coalesceMemberRuns("
            + "['a','b','c','d'],"
            + "{a:{path:'x.ts',line:10,change:'added'},"
            + "b:{path:'x.ts',line:11,change:'added'},"
            + "c:{path:'x.ts',line:13,change:'added'},"
            + "d:{path:'y.ts',line:1,change:'added'}});"
            + "assert.strictEqual(runs.length,3);"
            + "assert.strictEqual(runs[0].startLine,10);"
            + "assert.strictEqual(runs[0].endLine,11);"
            + "assert.strictEqual(runs[0].memberIds.length,2);"
            + "assert.strictEqual(runs[1].startLine,13);"
            + "assert.strictEqual(runs[1].endLine,13);"
            + "assert.strictEqual(M.inventoryMode(null), 'git-diff');"
            + "assert.strictEqual(M.inventoryMode({mode:'file-set'}), 'file-set');"
            + "assert.deepStrictEqual(M.searchNodes([['file:aa',{path:'x'}]], ''), []);"
            + "assert.ok(M.searchNodes([['file:zz',{path:'p'}]], 'ile').some(e=>e[0]==='file:zz'));"
            + "const ranked=M.searchNodes([['file:zz',{path:'aa'}],['x:aa',{path:'z'}]],'aa');"
            + "assert.strictEqual(ranked[0][0],'file:zz');"
            + "const led={o1:{state:'covered',disposition:{kind:'semantic',logic:[],consumers:[]}},"
            + "o2:{state:'covered',disposition:{kind:'semantic',logic:['T'],consumers:[]}}};"
            + "const by={o1:{obligationId:'o1'},o2:{obligationId:'o2'}};"
            + "const gs=M.flowGroups(['o1','o2'],by,led);"
            + "assert.ok(gs.some(g=>g.title==='(untitled flow)'));"
            + "const lay=M.layoutNodes([['b',{hop:1}],['a',{hop:0}],['c',{hop:1}]], 2);"
            + "assert.strictEqual(lay['a'].x,0);"
            + "assert.strictEqual(lay['b'].x,280);"
            + "assert.ok(lay['b'].y < lay['c'].y);"
            + "const sn=M.snippetSync({lineText:'hi',line:1,path:'a.ts'});"
            + "assert.strictEqual(sn.text,'hi'); assert.strictEqual(sn.needRepo,false);"
            + "const del=M.snippetSync({change:'deleted',path:'a.ts',line:1});"
            + "assert.strictEqual(del.unavailable,true); assert.strictEqual(del.needRepo,false);"
            + "const entries=[['file:zz',{path:'zz.ts',hop:9}],['file:aa',{path:'aa.ts',hop:0}],"
            + "['sym:Q',{qualname:'Pkg.Q',hop:1}]];"
            + "const hits=M.searchNodes(entries,'aa');"
            + "assert.strictEqual(hits[0][0],'file:aa');"
            + "assert.ok(M.searchNodes(entries,'zz').some(e=>e[0]==='file:zz'));"
        )

    def test_app_js_syntax(self):
        if not shutil.which("node"):
            self.skipTest("node required")
        app = Path(__file__).resolve().parent.parent / "viewer" / "app.js"
        r = subprocess.run(
            ["node", "--check", str(app)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_hr_and_change_filter(self):
        self._run_node(
            "const hrs=[{phase:'graph',kind:'k',obligationId:null},"
            + "{phase:'x',kind:'k2',obligationId:'o1',componentId:'c',packetId:'p'}];"
            + "assert.strictEqual(M.runLevelHardRejects(hrs).length,1);"
            + "assert.deepStrictEqual(M.hardRejectsForSelection(hrs,['o1']).map(h=>h.kind),['k2']);"
            + "assert.strictEqual(M.changeFilterMatch('added','added','git-diff'), true);"
            + "assert.strictEqual(M.changeFilterMatch('present','added','file-set'), false);"
            + "assert.strictEqual(M.changeFilterMatch('present','present','file-set'), true);"
            + "assert.strictEqual(M.inventoryMode(null), 'git-diff');"
        )

if __name__ == "__main__":
    unittest.main()
