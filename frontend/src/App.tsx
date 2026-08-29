import { Routes, Route, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import HomePage from "@/pages/HomePage";
import FundDetailPage from "@/pages/FundDetailPage";
import Layout from "@/components/Layout";

const EASE_OUT: [number, number, number, number] = [0.23, 1, 0.32, 1];

export default function App() {
  const location = useLocation();

  return (
    <Layout>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.22, ease: EASE_OUT }}
        >
          <Routes location={location}>
            <Route path="/" element={<HomePage />} />
            <Route path="/fund/:schemeCode" element={<FundDetailPage />} />
          </Routes>
        </motion.div>
      </AnimatePresence>
    </Layout>
  );
}
