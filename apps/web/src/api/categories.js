import request from '../utils/request.js'

/**
 * 获取随当前版本发布的只读分类树。
 * 自动分类的新候选直接用于当前发布流程，不会改写应用文件。
 */
export const fetchCategories = () => request.get('/xianyu/categories')
