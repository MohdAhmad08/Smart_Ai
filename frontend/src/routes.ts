import { createBrowserRouter } from 'react-router-dom';
import { RootLayout } from './components/RootLayout';
import { ProductionFloorView } from './components/ProductionFloorView';
import { EnhancedAnalyticsView } from './components/EnhancedAnalyticsView';
import { DatabaseView } from './components/DatabaseView';

export const router = createBrowserRouter([
  {
    path: '/',
    Component: RootLayout,
    children: [
      { index: true, Component: ProductionFloorView },
      { path: 'analytics', Component: EnhancedAnalyticsView },
      { path: 'database', Component: DatabaseView },
    ],
  },
]);
