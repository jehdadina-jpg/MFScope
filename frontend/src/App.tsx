import { Routes, Route } from "react-router-dom";
import HomePage from "@/pages/HomePage";
import FundDetailPage from "@/pages/FundDetailPage";
import Layout from "@/components/Layout";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/fund/:schemeCode" element={<FundDetailPage />} />
      </Routes>
    </Layout>
  );
}
