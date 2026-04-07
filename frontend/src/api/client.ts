import axios from 'axios'
import { useTeacherStore } from '@/stores/teacher'
import { useStudentStore } from '@/stores/student'
import { API_BASE_URL } from './config'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
})

apiClient.interceptors.request.use((config) => {
  const teacherToken = useTeacherStore().token
  const studentToken = useStudentStore().token
  const token = teacherToken ?? studentToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export default apiClient
