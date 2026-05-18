import React, { useEffect, useState } from "react";
import axios from "axios";

type Tier = "hot" | "warm" | "cold" | "archive";

interface ArchivedFile {
  id: number;
  filename: string;
  file_size_bytes: number;
  seaweedfs_fid: string;
  archived_at: string;
}

const GB = 1024 ** 3;
const fmt = (b: number) => b >= GB
  ? (b / GB).toFixed(2) + " GB"
  : (b / 1024 / 1024).toFixed(1) + " MB";

const TierManagement: React.FC<{ projectId: number }> = ({ projectId }) => {
  const [archived, setArchived] = useState([]);
  const [selected, setSelected] = useState([]);
  const [targetTier, setTargetTier] = useState("warm");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    axios.get(`/api/v1/archive/list/${projectId}`)
      .then(r => setArchived(r.data))
      .catch(e => setMessage("Failed to load archived files: " + e.message));
  }, [projectId]);

  const toggle = (id: number) =>
    setSelected(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );

  const handleOverride = async () => {
    if (selected.length === 0) return;
    setBusy(true);
    try {
      const resp = await axios.post("/api/v1/retention/override-tier", {
        output_ids: selected,
        target_tier: targetTier,
      });
      setMessage(
        `Migrated ${resp.data.success} files to ${targetTier.toUpperCase()}`
        + (resp.data.errors > 0 ? ` (${resp.data.errors} errors)` : "")
      );
      setSelected([]);
    } catch (e: any) {
      setMessage("Migration failed: " + e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleRestore = async (id: number) => {
    setBusy(true);
    try {
      await axios.post("/api/v1/archive/restore", { output_id: id });
      setArchived(prev => prev.filter(f => f.id !== id));
      setMessage(`File ${id} restored to HOT tier`);
    } catch (e: any) {
      setMessage("Restore failed: " + e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    
      
        Tier Management — Project {projectId}
      

      {message && (
        
          {message}
        
      )}

      
         setTargetTier(e.target.value as Tier)}
          style={{ padding: "6px 10px", borderRadius: 3,
                   border: "1px solid #c0a0e0", fontSize: 13 }}>
          HOT (NVMe)
          WARM (SSD)
          COLD (HDD)
          ARCHIVE (slow HDD)
        
        
          {busy ? "Migrating…" : `Move ${selected.length} selected → ${targetTier.toUpperCase()}`}
        
      

      
        Archived Files ({archived.length})
      
      {archived.length === 0 ? (
        No archived files.
      ) : (
        
          
            
              
                
                    setSelected(
                      selected.length === archived.length
                        ? [] : archived.map(f => f.id)
                    )
                  }
                />
              
              File
              Size
              
                Archived At
              Action
            
          
          
            {archived.map((f, i) => (
              
                
                   toggle(f.id)} />
                
                
                  {f.filename}
                  
                    FID: {f.seaweedfs_fid}
                
                
                  {fmt(f.file_size_bytes)}
                
                  {new Date(f.archived_at).toLocaleDateString()}
                
                   handleRestore(f.id)} disabled={busy}
                    style={{ background: "#7722cc", color: "#fff",
                             border: "none", borderRadius: 3,
                             padding: "3px 10px", cursor: "pointer",
                             fontSize: 11 }}>
                    Restore to HOT
                  
                
              
            ))}
          
        
      )}
    
  );
};

export default TierManagement;
