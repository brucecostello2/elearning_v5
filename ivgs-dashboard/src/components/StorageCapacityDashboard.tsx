import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";

interface TierData {
  used_bytes: number;
  free_bytes: number;
  file_count: number;
  utilisation_pct: number;
}

interface CapacityReport {
  timestamp: string;
  tiers: { hot: TierData; warm: TierData; cold: TierData; archive: TierData };
  dedup_ratio: {
    ratio: number;
    saved_bytes: number;
    unique_files: number;
    total_references: number;
  };
}

const GB = 1024 ** 3;
const fmt = (b: number) => (b / GB).toFixed(1) + " GB";

const TIER_COLORS: Record = {
  hot: "#1a0a3d",
  warm: "#4a1a8c",
  cold: "#6633aa",
  archive: "#9966dd",
};

const TierBar: React.FC<{ tier: string; data: TierData }> = ({ tier, data }) => {
  const pct = data.utilisation_pct;
  const color = pct >= 90 ? "#cc3300" : pct >= 75 ? "#e07800" : TIER_COLORS[tier];
  return (
    
      
        {tier.toUpperCase()}
        
          {fmt(data.used_bytes)} / {fmt(data.used_bytes + data.free_bytes)}
           · {data.file_count.toLocaleString()} files
        
      
      
        
      
      
        {pct.toFixed(1)}% utilised
        {pct >= 90 && 
          ⚠ CRITICAL}
        {pct >= 75 && pct < 90 && 
          ⚠ WARNING}
      
    
  );
};

const StorageCapacityDashboard: React.FC = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await axios.get(
        "/api/v1/storage-analytics/capacity"
      );
      setData(resp.data);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60_000); // refresh every 60s
    return () => clearInterval(id);
  }, [load]);

  if (loading && !data) return Loading...;
  if (error) return {error};
  if (!data) return null;

  const tiers = ["hot", "warm", "cold", "archive"] as const;

  return (
    
      
        Storage Capacity — SeaweedFS Cluster
      
      
        Last updated: {new Date(data.timestamp).toLocaleString()}
         · 
        
          Refresh
        
      

      {tiers.map(t => (
        
      ))}

      
        
          Deduplication Efficiency
        
        
          
            
              Space saved
              
                {fmt(data.dedup_ratio.saved_bytes)}
              
            
            
              
                Deduplication ratio
              
                {data.dedup_ratio.ratio.toFixed(1)}%
              
            
            
              
                Unique files
              
                {data.dedup_ratio.unique_files.toLocaleString()}
            
            
              
                Total references
              
                {data.dedup_ratio.total_references.toLocaleString()}
            
          
        
      
    
  );
};

export default StorageCapacityDashboard;
