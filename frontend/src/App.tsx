import React from 'react';
import { Routes, Route, NavLink } from 'react-router-dom';
import { Upload, Table2, BarChart3, Download, Microscope } from 'lucide-react';
import UploadPage from './pages/UploadPage';
import MappingReview from './pages/MappingReview';
import OntologyReview from './pages/OntologyReview';
import QualityDashboard from './pages/QualityDashboard';
import ExportPage from './pages/ExportPage';

const NAV_ITEMS = [
  { to: '/', icon: Upload, label: 'Upload' },
  { to: '/review', icon: Table2, label: 'Mapping Review' },
  { to: '/ontology', icon: Microscope, label: 'Ontology' },
  { to: '/quality', icon: BarChart3, label: 'Quality' },
  { to: '/export', icon: Download, label: 'Export' },
];

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <span className="text-2xl">🔬</span>
              <h1 className="text-xl font-bold text-gray-900">
                Meta<span className="text-primary-600">Harmonizer</span>
              </h1>
              <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded-full font-medium">
                v0.1.0
              </span>
            </div>

            <nav className="flex gap-1">
              {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) =>
                    `flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors
                    ${isActive
                      ? 'bg-primary-50 text-primary-700'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'}`
                  }
                >
                  <Icon className="w-4 h-4" />
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/review" element={<MappingReview />} />
          <Route path="/review/:studyId" element={<MappingReview />} />
          <Route path="/ontology" element={<OntologyReview />} />
          <Route path="/ontology/:studyId" element={<OntologyReview />} />
          <Route path="/quality" element={<QualityDashboard />} />
          <Route path="/quality/:studyId" element={<QualityDashboard />} />
          <Route path="/export" element={<ExportPage />} />
          <Route path="/export/:studyId" element={<ExportPage />} />
        </Routes>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 py-4 text-center text-xs text-gray-400">
        MetaHarmonizer Dashboard &middot; Biomedical Metadata Harmonization &middot; cBioPortal Compatible
      </footer>
    </div>
  );
}
