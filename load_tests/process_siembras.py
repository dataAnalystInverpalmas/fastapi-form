import mysql.connector
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime

# Add the parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

# Import database module
from core.database import DataBase

def transform_siembra_data():
    """Transform siembra data from database"""
    db = DataBase(show_gui_messages=False)
    
    if not db.connect():
        print("Failed to connect to database")
        return None
    
    print("\nMySQL Connector version:", mysql.connector.__version__)
    
    # Main query with improved error handling
    select_query = """
    SELECT 
        p.finca, p.bloque, p.nave, p.tabla, p.cama, p.variedad, 
        d.aass as fecha_siembra, p.plantas, p.nmanguera, p.tipo_suelo, 
        p.ferradica as fecha_arranque, 
        CASE 
            WHEN p.tipo_siembra='1PICO' THEN 1 
            WHEN p.tipo_siembra='REEMPLAZO' THEN 1 
            ELSE 2 
        END as ciclos 
    FROM plane as p 
    LEFT JOIN dates as d ON d.fecha = p.fecha_siembra
    WHERE p.plantas > 1
    """
    
    print("\nExecuting main query...")
    
    results = db.execute_query(select_query)
    
    if not results:
        print("\nERROR: No data returned from main query. Possible issues:")
        print("- No records with plantas > 1")
        print("- No matching dates in dates table")
        print("- Data might need to be imported")
        return None
    
    print(f"\nSuccess: Retrieved {len(results)} records")
    
    # Create DataFrame with type hints
    df = pd.DataFrame(results)
    print("Datos iniciales")
    print(df.head(2))

    # Data validation
    if df.empty:
        print("Warning: DataFrame created but empty")
        return None
    
    # Filter specific rows
    filter_mask = ~(
        (df['finca'] == 'INVERPALMAS') & 
        (df['bloque'] == 16) & 
        (df['nave'] == 10) & 
        (df['variedad'] != 'MISS TRENDY')
    )

    df = df[filter_mask]
    
    # Data transformations
    try:
        # Initial transformations
        df['fecha_arranque'] = df['fecha_arranque'].astype(str).str[:]
        df['fecha_siembra'] = df['fecha_siembra'].astype(str).str[:]
        df['tipo_suelo'] = df['tipo_suelo'].str.replace(' ', '_')
        df['ciclos'] = df['ciclos'].astype(str).str[:]
        
        # Define mappings - UPDATED TO MATCH SECOND CODE
        cascarilla_map = {
            'CASCARILLA_PRIMER_USO': 'NNUEVA',
            'CASCARILLA_SEGUNDO_USO': '2SEGUNDO_USO',
            'CASCARILLA_TERCER_USO': '3TERCER_USO',
            'CASCARILLA_CUARTO_USO': '4CUARTO_USO'
        }
        
        goteo_map = {
            'Gotero Externo (2.0 l/h - 0.3m)': 'GOTERO_EXTERNO_(2.0_L/H_-_0.3M)',
            'Gotero Interno (1.2 l/h - 0.2m)': 'GOTERO_INTERNO_(1.2_L/H_-_0.2M)',
            'Gotero Externo (2.0 l/h - 0.2m)': 'GOTERO_EXTERNO_(2.0_L/H_-_0.2M)',
            'Gotero Interno (1.0 l/h - 0.2m)': 'GOTERO_INTERNO_(1.0_L/H_-_0.2M)'
        }
        
        # Apply goteo mapping with default value
        df['goteo'] = df['nmanguera'].map(goteo_map).fillna('GOTERO_EXTERNO_(1.0_L/H_-_0.2M)')
        
        # Apply cascarilla mapping with default value
        df['cascarilla'] = df['tipo_suelo'].map(cascarilla_map).fillna('NNUEVA')
        
        # Extract week and year
        df['semana'] = df['fecha_siembra'].str[-2:].str.zfill(2)
        df['año'] = "20" + df['fecha_siembra'].str[:2]
        
        # Final column selection and renaming
        final_df = df[[
            'finca', 'bloque', 'nave', 'tabla', 'cama', 'variedad',
            'semana', 'año', 'plantas', 'ciclos', 'cascarilla', 'goteo'
        ]].rename(columns={
            'plantas': 'cantidad',
            'ciclos': 'ciclo'
        })
        
        return final_df
        
    except Exception as e:
        print(f"Error during data transformation: {str(e)}")
        return None

def export_to_excel(df, output_path):
    """Export DataFrame to Excel with error handling"""
    try:
        # Create backup of previous file
        backup_path = output_path.replace('.xlsx', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx')
        
        # Write to temporary file first
        temp_path = output_path + '.temp.xlsx'
        df.to_excel(temp_path, index=False)
        
        # If successful, rename temp file to final destination
        Path(temp_path).replace(output_path)
        
        print(f"\nSuccess: File saved to {output_path}")
        print(f"Backup created at: {backup_path}")
        return True
        
    except PermissionError:
        print("\nERROR: Permission denied. Please close the Excel file if open.")
    except Exception as e:
        print(f"\nERROR saving file: {str(e)}")
    
    return False

def main():
    """Main execution function"""
    print("=== Starting Siembra Data Processing ===")
    print(f"Start time: {datetime.now()}")
    
    siembra_df = transform_siembra_data()
    
    if siembra_df is not None:
        print("\nData Summary:")
        print(f"- Total records: {len(siembra_df)}")
        print(f"- Columns: {list(siembra_df.columns)}")
        print(siembra_df.head(2))
        
        output_path = "//svrinverpalmas/usuarios/produccion/Sofia/tika/plano nuevo siembra.xlsx"
        success = export_to_excel(siembra_df, output_path)
        
        if success:
            print("\nProcess completed successfully")
        else:
            print("\nProcess completed with errors")
    else:
        print("\nProcess aborted - no data to export")
    
    print(f"\nEnd time: {datetime.now()}")

if __name__ == "__main__":
    main()