import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import StudentView from './StudentView'
import InstructorView from './InstructorView'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/student" element={<StudentView />} />
        <Route path="/instructor" element={<InstructorView />} />
        <Route path="*" element={<Navigate to="/student" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
