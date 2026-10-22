"""Per-platform completion contract shared by CLI, reports and the skill agent."""
from .core import PLATFORMS, safe_url, target_count


def login_prompt(platform, state):
    url = safe_url(state.get('loginLink'), platform) or safe_url(state.get('url'), platform) or PLATFORMS[platform]['home']
    return (f'请先在 Tabbit 登录【{PLATFORMS[platform]["name"]}】：{url}。'
            '验证码请手动完成；登录后告诉我“已登录”，我会继续这个平台。'
            '如果暂时不搜，也请明确告诉我跳过；不会把未登录记为零岗位或默认跳过。')


def platform_progress(plan, jobs, statuses):
    rows = []
    for key in plan['platforms']:
        state = statuses.get(key, {'status': 'not_scanned'})
        mine = [j for j in jobs if j['platform'] == key]
        qualified = sum(j['bucket'] == 'shortlist' for j in mine)
        review = sum(j['bucket'] == 'review' for j in mine)
        target = target_count(plan, key)
        missing = max(0, target - qualified)
        status = state.get('status', 'not_scanned')
        url = safe_url(state.get('loginLink'), key) or safe_url(state.get('url'), key) or PLATFORMS[key]['home']
        if status == 'skipped' and state.get('note'):
            action, message = 'shortfall', '用户明确跳过此平台：' + state['note']
        elif status == 'login_required':
            action, message = 'ask_login', login_prompt(key, state)
        elif status in ('model_rate_limited','host_rate_limited','platform_rate_limited'):
            action = 'pause_platform' if status=='platform_rate_limited' else 'pause_model'
            message = ('招聘平台明确返回 HTTP 429，停止该平台请求，按 Retry-After 或后续明确恢复指令继续，不要求重新登录。'
                       if status=='platform_rate_limited' else
                       'Codex/宿主请求链路限流，暂停本轮自动调用并保留进度；不要切换平台、创建子 Agent 或循环重试，也不要让用户重新登录招聘平台。')
        elif status == 'anti_bot_cooldown':
            action = 'pause_platform'
            message = ('平台把自动化页面立即置为 about:blank（反自动化反制）。停止读取、刷新和反复检查已有标签；'
                       '已捕获证据保留在报告中。这不是未登录，不需要用户操作。'
                       '建议等待 20-30 分钟冷却后用一次性新页面低速恢复（scan --only 本平台），不从头重扫。')
        elif status in ('browser_error','wrong_context','browser_busy','access_denied'):
            action = 'inspect_existing_tab'
            message = {'browser_error':'Agent 先读取已有同平台标签，核实页面实际状态；空白页不证明未登录，不把浏览器排查交给用户。',
                       'wrong_context':'Agent 先从可见导航寻找求职入口；当前是招聘方页面，不是未登录，不填写企业认证表单。',
                       'browser_busy':'已有标签被其他任务占用，等待释放；不得新建标签或任务绕过占用。',
                       'access_denied':'Agent 只读核实已有页面的访问提示；只有真实验证码或登录墙才请用户操作。'}[status]
        elif status in ('blocked', 'app_required'):
            action = 'resolve_access'
            message = {'blocked': '平台要求验证或限制访问，请用户手动处理后恢复；本平台仍未完成。',
                       'app_required': '网页无法完成求职搜索，说明需要 App，并请用户提供岗位链接或明确跳过。'}[status]
        elif qualified >= target and status in ('ok', 'empty'):
            action, message = 'done', f'已找到 {qualified}/{target} 个符合条件的岗位。'
        elif status in ('not_scanned', 'guided_pending', 'needs_inspection', 'imported', 'ready'):
            action = 'tabbit_search'
            message = f'必须继续用 Tabbit 在{PLATFORMS[key]["name"]}执行已确认查询；目标 {target} 个。不能在只完成 BOSS/猎聘后结束。'
        elif missing:
            # Reaching a page limit is evidence only when explicitly recorded, not inferred from a low count.
            stop = state.get('stop_reason')
            if stop in ('results_exhausted', 'budget_exhausted'):
                action = 'shortfall'
                message = f'符合 {qualified}/{target} 个，待核实 {review} 个；停止原因：' + {
                    'results_exhausted':'当前查询已无更多结果', 'budget_exhausted':'达到已确认的浏览预算'}[stop] + '。如实交付不足，不降低条件凑数。'
            else:
                action = 'collect_more'
                message = f'还差 {missing} 个；继续翻页或核实候选详情。待核实 {review} 个不计入已满足数量。'
        else:
            action, message = 'verify_coverage', '数量已达到，但查询覆盖状态未确认；核对并记录实际完成的查询。'
        rows.append({'platform':key, 'name':PLATFORMS[key]['name'], 'target':target,
                     'qualified':qualified, 'review':review, 'missing':missing, 'status':status,
                     'action':action, 'message':message, 'url':url})
    return rows


def next_actions(plan, jobs, statuses):
    rows = platform_progress(plan, jobs, statuses)
    pending = [r for r in rows if r['action'] not in ('done', 'shortfall')]
    model_paused = any(r['action']=='pause_model' for r in rows)
    return {'complete':all(r['action'] == 'done' for r in rows),
            'execution_paused':model_paused,
            'can_deliver_final':not pending,
            'target_total':sum(r['target'] for r in rows),
            'qualified_total':sum(r['qualified'] for r in rows),
            'needs_user':[r['platform'] for r in pending if r['action'] in ('ask_login','resolve_access')],
            'needs_agent':[] if model_paused else [r['platform'] for r in pending if r['action'] not in ('ask_login','resolve_access','pause_model','pause_platform')],
            'deferred_until_resume':[r['platform'] for r in pending if r['action']!='pause_model'] if model_paused else [],
            'paused':[r['platform'] for r in pending if r['action'] in ('pause_model','pause_platform')],
            'platforms':rows}


def write_actions(out, plan, jobs, statuses):
    import json
    from pathlib import Path
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    actions = next_actions(plan, jobs, statuses)
    (out/'next-actions.json').write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 本轮还需要完成什么', '',
             f'目标 {actions["target_total"]} 个；已符合 {actions["qualified_total"]} 个。', '',
             '以下登录提示必须直接发给用户；界面搜索事项由 Agent 继续，不得静默省略平台。', '']
    for row in actions['platforms']:
        lines.extend([f'## {row["name"]} · {row["qualified"]}/{row["target"]}', '', row['message'], ''])
    (out/'next-actions.md').write_text('\n'.join(lines), encoding='utf-8')
    return actions
