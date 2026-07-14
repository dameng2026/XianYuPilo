import request from '../utils/request'

export function getCarouselList() {
  return request.get('/carousel/list', { suppressGlobalError: true })
}

export function getAnnouncementList() {
  return request.get('/announcement/list')
}
