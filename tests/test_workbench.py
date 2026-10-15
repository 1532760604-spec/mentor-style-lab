import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf
import workbench as wb

TEXT = ('We examine the relationship between service access and household outcomes. '
        'The analysis uses a synthetic sample of 120 households for a software demonstration only. '
        'These findings suggest a possible association, although the design does not establish a causal effect.')


def pdf_bytes(text=TEXT):
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_textbox((50,50,540,750),text,fontsize=12)
        return doc.tobytes()


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.project = wb.create_project('scholar-a','Scholar A',self.base)
        self.data = pdf_bytes()
        wb.import_pdfs(self.project,[('Study of service access and household outcomes.pdf',self.data)],'learning')
        self.pid = wb.read(self.project/'papers.json')[0]['paper_id']

    def excerpt(self, project=None, pid=None):
        return wb.add_excerpt(project or self.project,pid or self.pid,1,'abstract',TEXT,True,'coauthored; unconfirmed writing role')

    def profile(self):
        row=self.excerpt()
        sheet={'target_scholar':'Scholar A','rules':[{'id':'R1','section':'abstract',
               'observation':'The passage states the research task before its limitation.',
               'application':'Keep the identification limit alongside the finding.',
               'confidence':'low','status':'tentative','support_papers':1,
               'evidence':[{'excerpt_id':row['excerpt_id'],'quote':'does not establish a causal effect'}],
               'exceptions':['Only one synthetic example; not an author-specific finding.']}]}
        wb.save_profile(self.project,sheet)
        return sheet

    def test_project_isolation_and_path_boundary(self):
        other=wb.create_project('scholar-b','Scholar B',self.base)
        self.excerpt()
        self.assertEqual(wb.read(other/'papers.json'),[])
        self.assertEqual(wb.read(other/'excerpts.json'),[])
        with self.assertRaises(ValueError): self.excerpt(other)
        for slug in ('../escape','/escape','C:\\escape','a/b','A'):
            with self.assertRaises(ValueError): wb.create_project(slug,'X',self.base)
        with self.assertRaises(FileExistsError): wb.create_project('scholar-a','Other person',self.base)

    def test_duplicates_invalid_batch_and_role_conflict(self):
        result=wb.import_pdfs(self.project,[('../../renamed.pdf',self.data)],'learning')
        self.assertEqual(result['added'],0)
        with self.assertRaises(ValueError): wb.import_pdfs(self.project,[('copy.pdf',self.data)],'test')
        before=(self.project/'papers.json').read_bytes()
        with self.assertRaises(ValueError):
            wb.import_pdfs(self.project,[('valid.pdf',pdf_bytes(TEXT+' Further detail.')),('bad.pdf',b'not a pdf')],'learning')
        self.assertEqual(before,(self.project/'papers.json').read_bytes())
        with self.assertRaises(ValueError):
            wb.import_pdfs(self.project,[('Study of service access and household outcomes (2).pdf',pdf_bytes(TEXT+' Another version.'))],'test')

    def test_heldout_text_never_enters_learning_packet(self):
        secret='HELDOUT_SENTINEL do not learn from this paper.'
        wb.import_pdfs(self.project,[('Unrelated final test.pdf',pdf_bytes(secret))],'test')
        self.excerpt()
        packet=wb.learning_packet(self.project)
        self.assertNotIn(secret,packet)
        pid=wb.read(self.project/'papers.json')[-1]['paper_id']
        with self.assertRaises(ValueError): wb.add_excerpt(self.project,pid,1,'abstract',TEXT,True,'sole author')

    def test_visual_confirmation_and_source_match_required(self):
        with self.assertRaises(ValueError): wb.add_excerpt(self.project,self.pid,1,'abstract',TEXT,False,'sole author')
        with self.assertRaises(ValueError): wb.add_excerpt(self.project,self.pid,1,'abstract',TEXT.replace('120','220'),True,'sole author')
        with self.assertRaises(ValueError): wb.add_excerpt(self.project,self.pid,2,'abstract',TEXT,True,'sole author')
        row=self.excerpt()
        self.assertEqual(row['reviewer'],'user_self_report')
        with self.assertRaises(ValueError): self.excerpt()
        p=self.project/'papers'/(self.pid+'.pdf')
        p.write_bytes(pdf_bytes(TEXT+' Changed.'))
        with self.assertRaises(ValueError): wb.learning_packet(self.project)

    def test_profile_quote_and_project_validation(self):
        sheet=self.profile()
        bad=copy.deepcopy(sheet); bad['rules'][0]['evidence'][0]['quote']='certain causal effect'
        with self.assertRaises(ValueError): wb.save_profile(self.project,bad)
        bad=copy.deepcopy(sheet); bad['target_scholar']='Scholar B'
        with self.assertRaises(ValueError): wb.save_profile(self.project,bad)
        bad=copy.deepcopy(sheet); bad['rules'][0]['section']='results'
        with self.assertRaises(ValueError): wb.save_profile(self.project,bad)
        bad=copy.deepcopy(sheet); bad['rules'][0]['support_papers']=3
        with self.assertRaises(ValueError): wb.save_profile(self.project,bad)
        self.assertFalse(wb.current_profile(self.project)['interpretation_verified'])

    def test_versions_count_once(self):
        wb.import_pdfs(self.project,[('Study of service access and household outcomes (2).pdf',pdf_bytes(TEXT+' A later version.'))],'learning')
        sheet=self.profile()
        pid=wb.read(self.project/'papers.json')[-1]['paper_id']
        row=wb.add_excerpt(self.project,pid,1,'abstract',TEXT+' A later version.',True,'coauthored')
        sheet['rules'][0]['evidence'].append({'excerpt_id':row['excerpt_id'],'quote':'does not establish a causal effect'})
        good=wb.save_profile(self.project,sheet)
        self.assertEqual(good['checks'][0]['independent_papers'],1)
        sheet['rules'][0]['support_papers']=2
        with self.assertRaises(ValueError): wb.save_profile(self.project,sheet)

    def test_stale_profile_and_unsupported_section_blocked(self):
        self.profile()
        with self.assertRaises(ValueError): wb.create_task(self.project,'Task','methods',TEXT,'120 households')
        wb.import_pdfs(self.project,[('Different paper.pdf',pdf_bytes(TEXT+' More evidence.'))],'learning')
        pid=wb.read(self.project/'papers.json')[-1]['paper_id']
        wb.add_excerpt(self.project,pid,1,'abstract',TEXT+' More evidence.',True,'sole author')
        with self.assertRaises(ValueError): wb.current_profile(self.project)
        self.assertEqual(len(list((self.project/'profiles').glob('*.json'))),1)

    def test_end_to_end_packets_blindness_and_freeze(self):
        self.profile()
        task=wb.create_task(self.project,'Private task name','abstract',TEXT+' <script>alert(1)</script>','120 households\nNo causal identification.')
        folder=self.project/'tasks'/task['id']
        general=(folder/'general-task.md').read_text(encoding='utf-8')
        styled=(folder/'style-task.md').read_text(encoding='utf-8')
        self.assertNotIn('style_rules',general)
        self.assertNotIn('Scholar A',general)
        self.assertIn('style_rules',styled)
        source=task['original']
        with self.assertRaises(ValueError): wb.blind_review(self.project,task['id'],source,source,False,'Tester')
        with self.assertRaises(ValueError): wb.blind_review(self.project,task['id'],source.replace('120','220'),source,True,'Tester')
        result=wb.blind_review(self.project,task['id'],source,source,True,'Tester')
        blind=(result/'blind.html').read_text(encoding='utf-8')
        answer=wb.read(result/'answer.json')
        for forbidden in ('Private task name','Scholar A','"role"','<script>','style_rules'):
            self.assertNotIn(forbidden,blind)
        self.assertIn('&lt;script&gt;',blind)
        self.assertEqual({x['role'] for x in answer['items']},{'original','general','style'})
        for name,digest in wb.read(result/'freeze.json').items(): self.assertEqual(wb.checksum((result/name).read_bytes()),digest)
        second=wb.blind_review(self.project,task['id'],source,source,True,'Tester')
        self.assertNotEqual(result,second)
        (folder/'general-task.md').write_text('tampered',encoding='utf-8')
        with self.assertRaises(ValueError): wb.blind_review(self.project,task['id'],source,source,True,'Tester')


class AppSmokeTests(unittest.TestCase):
    def test_ui_upload_profile_task_and_blind_export(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            project=wb.create_project('scholar-a','Scholar A',base)
            wb.create_project('scholar-b','Scholar B',base)
            listing=wb.list_projects; location=wb.project_path
            with patch('workbench.list_projects',side_effect=lambda:listing(base)), \
                 patch('workbench.project_path',side_effect=lambda s,b=base:location(s,b)):
                app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=15).run()
                def widget(kind,label):
                    return next(item for item in getattr(app,kind) if item.label==label)
                def click(label):
                    widget('button',label).click().run()
                    self.assertEqual(len(app.exception),0)
                    self.assertEqual(len(app.error),0)
                app.file_uploader[0].set_value(('synthetic.pdf',pdf_bytes(),'application/pdf'))
                click('导入论文')
                self.assertEqual(len(wb.read(project/'papers.json')),1)
                app.radio[0].set_value('2 核对选段').run()
                widget('text_area','要学习的英文选段').set_value(TEXT)
                widget('checkbox','已核对原页、阅读顺序、页码和目标学者署名').check()
                click('保存选段')
                row=wb.read(project/'excerpts.json')[0]
                sheet={'target_scholar':'Scholar A','rules':[{'id':'R1','section':'abstract',
                       'observation':'State the task and qualify the conclusion.',
                       'application':'Preserve the limitation beside the finding.',
                       'confidence':'low','status':'tentative','support_papers':1,
                       'evidence':[{'excerpt_id':row['excerpt_id'],'quote':'does not establish a causal effect'}],
                       'exceptions':['Synthetic example only.']}]}
                app.radio[0].set_value('3 整理文风卡').run()
                widget('text_area','粘贴模型返回的 JSON 文风卡').set_value(json.dumps(sheet))
                click('检查出处并保存文风卡')
                app.radio[0].set_value('4 改写与盲评').run()
                widget('text_input','任务名称').set_value('Synthetic abstract')
                widget('text_area','待改英文原文').set_value(TEXT)
                widget('text_area','不能改动的研究信息，每行一条').set_value('120 households; association only.')
                click('保存任务并生成两份材料')
                self.assertEqual(len(wb.list_tasks(project)),1)
                widget('text_area','普通润色版英文正文').set_value(TEXT)
                widget('text_area','按文风卡改写的英文正文').set_value(TEXT)
                widget('text_input','由谁核对研究信息').set_value('Software test; identical synthetic text')
                widget('checkbox','已对照原文及两份主张核对结果，处理遗漏、增加和强度变化').check()
                click('生成三版匿名盲评')
                self.assertEqual(len(list((project/'reviews').glob('*/blind.html'))),1)
                widget('selectbox','选择学者项目').set_value('scholar-b').run()
                self.assertEqual(len(app.exception),0)
                self.assertEqual(wb.read(base/'scholar-b/papers.json'),[])
                self.assertNotIn(TEXT, '\n'.join(str(item.value) for item in app.text_area))

    def test_ui_project_creation_and_all_steps(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            create=wb.create_project; listing=wb.list_projects; location=wb.project_path
            with patch('workbench.list_projects',side_effect=lambda:listing(base)), \
                 patch('workbench.create_project',side_effect=lambda s,n:create(s,n,base)), \
                 patch('workbench.project_path',side_effect=lambda s,b=base:location(s,b)):
                app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=15).run()
                self.assertEqual(len(app.exception),0)
                app.text_input[0].set_value('Scholar B')
                app.text_input[1].set_value('scholar-b')
                app.button[0].click().run()
                self.assertEqual(len(app.exception),0)
                self.assertTrue((base/'scholar-b/project.json').exists())
                for step in ['2 核对选段','3 整理文风卡','4 改写与盲评','1 上传论文']:
                    app.radio[0].set_value(step).run()
                    self.assertEqual(len(app.exception),0,step)


if __name__ == '__main__': unittest.main()
