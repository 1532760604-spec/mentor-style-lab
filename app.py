"""Run with: python -m streamlit run app.py"""
from pathlib import Path
import streamlit as st
import workbench as wb

st.set_page_config(page_title='论文文风工作台', page_icon='📄', layout='wide')
st.title('论文文风工作台')
st.write('选一位你想学习的学者，从论文中整理写作习惯，再用同一段内容比较改写效果。')
st.caption('论文和项目保存在运行程序的电脑上。需要分析或改写时，由你把材料交给自己的聊天模型；程序不调用模型 API。')

with st.sidebar:
    st.subheader('你的项目')
    projects = wb.list_projects()
    ids = [p['id'] for p in projects]
    names = {p['id']: p['scholar'] for p in projects}
    selected = st.selectbox('选择学者项目', ids, format_func=lambda x: f'{names[x]} · {x}', index=ids.index(st.session_state.get('active_project')) if st.session_state.get('active_project') in ids else 0) if ids else None
    with st.expander('新建项目', expanded=not ids):
        with st.form('new_project'):
            scholar = st.text_input('学者姓名或代号', placeholder='你想学习的学者')
            slug = st.text_input('项目代号', placeholder='my-scholar', help='小写英文、数字、短横线或下划线；每位学者单独保存。')
            if st.form_submit_button('创建项目'):
                try:
                    wb.create_project(slug, scholar)
                    st.session_state['active_project'] = slug
                    st.rerun()
                except (ValueError, FileExistsError) as exc:
                    st.error('该项目代号已存在，请换一个。' if isinstance(exc, FileExistsError) else str(exc))
    st.caption('当前支持有文字层的英文 PDF。扫描件需先完成 OCR。')

if not selected:
    st.info('先在左侧创建项目。之后可以上传论文；不同项目的论文、文风卡和改写记录分别保存。')
    st.stop()
project = wb.project_path(selected)
config = wb.read(project/'project.json')
st.subheader(config['scholar'])
step = st.radio('当前步骤', ['1 上传论文', '2 核对选段', '3 整理文风卡', '4 改写与盲评'], horizontal=True, key=f'{selected}_step')


def download(label, content, name, mime='text/markdown', **kwargs):
    st.download_button(label, content, file_name=name, mime=mime, **kwargs)


if step == '1 上传论文':
    st.write('先上传希望用于学习的论文。准备几篇你熟悉的代表作即可，其他作者的文章和留作评估的文章请分开登记。')
    with st.form(f'{selected}_upload'):
        role = st.selectbox('这批论文的用途', list(wb.ROLES), format_func=wb.ROLES.get)
        uploaded = st.file_uploader('选择 PDF，可一次上传多份', type=['pdf'], accept_multiple_files=True)
        if st.form_submit_button('导入论文'):
            try:
                if not uploaded:
                    raise ValueError('请先选择 PDF。')
                with st.spinner('正在读取论文…'):
                    result = wb.import_pdfs(project, [(f.name, f.getvalue()) for f in uploaded], role)
                st.success(f"已新增 {result['added']} 份，项目中共 {result['total']} 份。同一文件不会重复保存。")
            except (ValueError, OSError) as exc:
                st.error(str(exc))
    papers = wb.read(project/'papers.json')
    if papers:
        st.dataframe([{'文件':p['filename'], '用途':wb.ROLES[p['role']], '页数':p['pages'], '文字较少的页':', '.join(map(str,p['low_text_pages'])) or '无'} for p in papers], hide_index=True)
        if (project/'version-candidates.json').exists() and wb.read(project/'version-candidates.json'):
            st.info('发现文件名相近的论文，暂按同文版本合并计数。请核对题目和 DOI；文件名不同的重复版本可能仍需你识别。')
    st.caption('上传只是登记。先确认目标学者署名，再选取具体段落；合著论文不等于全部由该学者执笔。')

elif step == '2 核对选段':
    papers = [p for p in wb.read(project/'papers.json') if p['role']=='learning']
    if not papers:
        st.info('请先上传目标学者的学习论文。')
        st.stop()
    options = {p['paper_id']:p for p in papers}
    pid = st.selectbox('选择论文', list(options), format_func=lambda x:options[x]['filename'], key=f'{selected}_paper')
    page_number = int(st.number_input('PDF 页序号（从 1 开始）', min_value=1, max_value=options[pid]['pages'], value=1, key=f'{selected}_{pid}_page'))
    try:
        raw, png = wb.source_page(project,pid,page_number)
    except (ValueError,OSError) as exc:
        st.error(str(exc)); st.stop()
    left,right = st.columns(2)
    with left:
        st.image(png, caption=f'PDF 第 {page_number} 页')
    with right:
        st.write('对照左侧原页，从下面抽取文字中复制一段完整正文。两栏排版可能顺序不对；保留原句，不要先润色。')
        st.text_area('该页自动抽取文字', value=raw, height=220, disabled=True, key=f'{selected}_{pid}_{page_number}_raw')
        with st.form(f'{selected}_{pid}_{page_number}_excerpt'):
            section = st.selectbox('章节', list(wb.SECTIONS),format_func=wb.SECTIONS.get)
            authorship = st.selectbox('目标学者的署名情况', ['待确认','独作','第一作者（执笔待确认）','通讯作者（执笔待确认）','其他合著（执笔待确认）','已确认参与本段写作'])
            text = st.text_area('要学习的英文选段',height=200)
            reviewed = st.checkbox('已核对原页、阅读顺序、页码和目标学者署名')
            if st.form_submit_button('保存选段'):
                try:
                    wb.add_excerpt(project,pid,page_number,section,text,reviewed,authorship)
                    st.success('选段已保存，可继续添加其他论文或章节。')
                except (ValueError,OSError) as exc:
                    st.error(str(exc))
    rows = wb.read(project/'excerpts.json')
    st.caption(f'已保存 {len(rows)} 段。只学一个章节也可以开始；以后再补充其他章节。')

elif step == '3 整理文风卡':
    st.write('下载学习包，交给你使用的聊天模型。它会按出处整理写作习惯，并返回 JSON 文风卡。再把结果粘贴回来，程序会检查引文和论文计数。')
    try:
        packet = wb.learning_packet(project)
        download('下载学习包', packet,'learning-packet.md')
        with st.expander('也可以直接复制内容'):
            st.code(packet,language='markdown')
    except (ValueError,OSError) as exc:
        st.info(str(exc)); st.stop()
    with st.form(f'{selected}_profile'):
        response = st.text_area('粘贴模型返回的 JSON 文风卡',height=280)
        if st.form_submit_button('检查出处并保存文风卡'):
            try:
                result = wb.save_profile(project,wb.parse_json(response))
                st.success(f"已保存 {len(result['sheet']['rules'])} 条规则。引文存在不代表解释正确，请阅读规则本身。")
            except (ValueError,OSError) as exc:
                st.error(str(exc))
    try:
        profile = wb.current_profile(project)
        for rule in profile['sheet']['rules']:
            with st.expander(f"{wb.SECTIONS[rule['section']]} · {rule['observation']}"):
                st.write(rule['application'])
                st.write('反例或限制：', rule['exceptions'])
        download('下载当前文风卡', __import__('json').dumps(profile,ensure_ascii=False,indent=2),'style-profile.json','application/json')
    except (ValueError,OSError) as exc:
        st.caption(str(exc))
    st.caption('材料会随学习包交给你选择的模型。发送前请确认这些选段可以提供给该服务。原 PDF 不会由本程序自动上传到外部服务。')

else:
    st.write('先新建一段改写任务，再分别生成普通润色和按文风卡改写的版本。已有任务保存在下面，切换项目后也可以继续。')
    with st.form(f'{selected}_task'):
        title = st.text_input('任务名称',placeholder='例如：第一篇对比稿的摘要')
        section = st.selectbox('要改写的章节',list(wb.SECTIONS),format_func=wb.SECTIONS.get)
        original = st.text_area('待改英文原文',height=200)
        claims = st.text_area('不能改动的研究信息，每行一条',height=150,placeholder='例如：样本量、国家、模型、比较对象、效果方向、显著性和限定语。此处请填自己文章的事实。')
        if st.form_submit_button('保存任务并生成两份材料'):
            try:
                result = wb.create_task(project,title,section,original,claims)
                st.success('任务已保存。下方选择这项任务，分别下载两份材料。')
            except (ValueError,OSError) as exc:
                st.error(str(exc))
    tasks = wb.list_tasks(project)
    if not tasks:
        st.stop()
    by_id = {t['id']:t for t in tasks}
    tid = st.selectbox('已保存的任务',list(by_id),format_func=lambda x:f"{by_id[x]['title']} · {x[:6]}",index=len(tasks)-1,key=f'{selected}_task_pick')
    task = by_id[tid]
    folder = project/'tasks'/tid
    st.write('建议在两个新的对话中分别使用两份材料。普通润色的对话只看普通任务包，以免受到作者画像影响。')
    a,b = st.columns(2)
    with a: download('下载普通润色任务', (folder/'general-task.md').read_bytes(),'general-task.md')
    with b: download('下载文风改写任务', (folder/'style-task.md').read_bytes(),'style-task.md')
    with st.expander('查看本任务原文与主张清单'):
        st.text(task['original'])
        for claim in task['claims']: st.write(claim['id'],claim['claim'])
    with st.form(f'{selected}_{tid}_review'):
        general = st.text_area('普通润色版英文正文',height=180)
        styled = st.text_area('按文风卡改写的英文正文',height=180)
        checker = st.text_input('由谁核对研究信息',placeholder='本人，或所用工具及是否另经人工核验')
        checked = st.checkbox('已对照原文及两份主张核对结果，处理遗漏、增加和强度变化')
        if st.form_submit_button('生成三版匿名盲评'):
            try:
                wb.blind_review(project,tid,general,styled,checked,checker)
                st.success('已生成新的盲评文件，编号和答案单独保存。旧轮次没有覆盖。')
            except (ValueError,OSError) as exc:
                st.error(str(exc))
    reviews = sorted((project/'reviews').glob('*/answer.json'), key=lambda path: wb.read(path)['created_at'])
    for path in reversed(reviews):
        answer = wb.read(path)
        if answer['task']['id'] != tid: continue
        with st.expander('盲评记录 '+answer['created_at'][:19]+' UTC',expanded=path==reviews[-1]):
            download('下载给评阅人的匿名稿', (path.parent/'blind.html').read_bytes(),'blind.html','text/html',key=path.parent.name+'_blind')
            st.caption('打开 HTML 即可阅读，也可用浏览器“打印 → 保存为 PDF”。论文片段较长时会自然续页。')
            download('下载版本答案（自己保管）',path.read_bytes(),'answer.json','application/json',key=path.parent.name+'_answer')
    st.caption('盲评比较的是写法和文字质量。数字检查只检查数字形式与次数，不能代替研究含义核对。')
