import request from '../utils/request.js'

const REMOVED_WORKFLOW_STATS = {
  workflowCount: 0,
  enabledCount: 0,
  todayExecutionCount: 0,
  successRate: 0,
  removed: true,
}

export const workflowOverview = async () => ({ data: REMOVED_WORKFLOW_STATS })

export const listWorkflowExecutions = async () => ({ data: { records: [], removed: true } })

export const aiRewriteGoods = data => request.post('/ai-tools/rewrite-goods', data || {})
