import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

arr = [0,0,0,0.01,0.04,0.1,0.25,0.48,0.65,0.82,0.83,0.75,0.59,0.43,0.3,0.18,0.12,0.1,0.06,0.04,0.03,0.02,0.01,0,0,0,0,0,0.01,0.02,0.05,0.07,0.12,0.17,0.24,0.3,0.37,0.43,0.46,0.48,0.49,0.46,0.45,0.44,0.37,0.31,0.31,0.23,0.18,0.11,0.08,0.06,0.07,0.05,0.04,0.09,0.08,0.1,0.09,0.07,0.11,0.09,0.07,0.1,0.11,0.14,0.13,0.21,0.24,0.25,0.3,0.3,0.27,0.31,0.36,0.3,0.3,0.33,0.24,0.18,0.19,0.15,0.17,0.12,0.13]

EDAD_INI = 18
SEM_VALLE = 8

def datos_curva(curva):
  """_Recibe curva para suavizar_

  Args:
      curva (_array_): _recibe una curva y la suaviza, devuelve curva suavizada_
  """
  #diccionario con los ciclos y datos para usar de acuerdo a estos se define la curva final
  dic = {
    23: [-4,6,8], 24: [-4,6,8], 25: [-3,6,8], 26: [-2,7,8], 27: [-1,7,8],
    28: [0,7,7], 29: [1,8,6], 30: [2,8,6], 31: [3,8,6], 32: [4,8,6]
  }
  
  
  curva = np.array(curva)
  t_lista = 0
  i_final = 0
  largo = len(curva)
        
        
#recorrer la curva y hallar curvas más altas y ciclo
  for i in range(largo):
    lista = list(curva[i:i+4])
    res = np.sum(lista)
    if res > t_lista:
      t_lista = res
      i_final = i + 3


  ppi_zeros = i_final - dic.get(i_final + EDAD_INI)[1] 
  ppf_izeros = i_final + dic.get(i_final + EDAD_INI)[2]
  ppf_fzeros = i_final + 8 + SEM_VALLE
  
  spf_izeros = ((ppf_izeros) * 2) + EDAD_INI + dic.get(i_final + EDAD_INI)[0]
  spf_fzeros = spf_izeros + SEM_VALLE
  
  np.set_printoptions(precision=2)  # For compact display.
  #en el primer array se suaviza el primer pico
  
  
  try:
    savgol_filter(curva[:ppf_izeros + int(SEM_VALLE/2)],3,2)
  except:
    a = np.array([])
  else:
    a = np.array(savgol_filter(curva[:ppf_izeros + int(SEM_VALLE/2)],3,2))
  #en el segundo array se suzavizan 2do
  
  
  try:
    savgol_filter(curva[ppf_izeros + int(SEM_VALLE/2):spf_fzeros],5,2)
  except:
    b = np.array([])
  else:
    b = np.array(savgol_filter(curva[ppf_izeros + int(SEM_VALLE/2):spf_fzeros],5,2))
  #3er pico array para suavizar
  
  
  try:
    savgol_filter(curva[spf_fzeros:],5,2)
  except:
    c = np.array([])
  else:
    c = np.array(savgol_filter(curva[spf_fzeros:],5,2))
  
  result = np.array(np.concatenate((a,b,c)))

  #poner ceros en donde corresponda
  for i in range(largo):
    if (i<ppi_zeros) or (i>ppf_izeros and i<=ppf_fzeros) or (i >= spf_izeros and i <= spf_fzeros):
      result[i] = 0
      
  #si el num es negativo pone un cero
  result = zeros(result)

  #c = np.array(result[:spf_fzeros+1])
  #d = np.array(dist_3pico)
  try:
    savgol_filter(result[:ppf_izeros + int(SEM_VALLE/2)],3,2)
  except:
    c = np.array([])
  else:
    c = np.array(savgol_filter(result[:ppf_izeros + int(SEM_VALLE/2)],3,2))
  #/////////////////////////////////////////////////////////////////////////////////#
  try:
    savgol_filter(result[ppf_izeros + int(SEM_VALLE/2):spf_fzeros],5,2)
  except:
    d = np.array([])
  else:
    d = np.array(savgol_filter(result[ppf_izeros + int(SEM_VALLE/2):spf_fzeros],5,2))
  #--------------------------------------------------------#
  try:
    savgol_filter(result[spf_fzeros:],5,2)
  except:
    e = np.array([])
  else:
    e = np.array(savgol_filter(result[spf_fzeros:],5,2))

  nresult = np.concatenate((c,d,e))
  
  #poner ceros en donde corresponda
  for i in range(largo):
    if (i<ppi_zeros) or (i>ppf_izeros and i<=ppf_fzeros) or (i >= spf_izeros and i <= spf_fzeros):
      nresult[i] = 0
  #si el num es negativo pone un cero
  nresult = zeros(nresult)

  return result,i_final,nresult

def zeros(x):
    nx = []
    x = np.array(x)
    for i in x:
        if i < 0:
            nx.append(abs(i))
        else:
            nx.append(i)
    return np.array(nx)

#----------------OTRAS  FUNCIONES  ------------------------------#

def dist_curve(df,flor,ciclo,pico):
    """
    """
    df = df[df['cflor']==flor]
    df = df[df['ciclo']==ciclo]
    df = df[df['pico']==pico]
    x = df.groupby('edad')['fm_real'].mean()
    dist = np.array(list(map(lambda i: i/sum(x),x)))
    return np.array(dist)
    #No se está usando
  

def curve_ini(df_group):
    edades = np.arange(18,70)
    edades_f = df_group.edad.unique()
    
    arreglo = []
    for z in edades:
        if z in edades_f:
            ys = df_group.query(f'edad=={z}')['fm_aj'].iloc[0]#columna para calcular en grafico principal
            arreglo.append(ys)
        else:
            arreglo.append(0)
            
    return arreglo

#----------------------CREAR DATAFRAME---------------------------#
def create_DF(dir,sheet):
    """_crea un dataframe_

    Args:
        dir (_type_): _ruta del archivo en excel_
        sheet (_type_): _hoja de datos para el dataframe_

    Returns:
        _type_: _dataframe_
    """
    df = pd.read_excel(dir, sheet_name=sheet, na_values=['(en blanco)'])
    #df = pd.DataFrame(df)
    return df
#-----------------------------------------------------------------#

#funcion nombre de finca
def nfinca(finca):
    if finca==1:
        nfinca='Palmas'
    elif finca==2:
        nfinca='Palermo'
    else:
        nfinca='Inverpalmas'
    return nfinca
#------------------------...........................................#
def welcome():
    print('*'*40)
    print('Bienvenido \nGenerador de Curvas - Inverpalmas')
    print('*'*40)

def goodbye():
    print('*'*40)
    print("Hasta luego!")
    print('*'*40)

    
#-----------------------------------------------------------#
#----------------------CREAR DATAFRAME---------------------------#
def create_DF(dir,sheet,ncolumns,convert):
    """
        dir: directorio del archivo excel,
        sheet: nombre de la hoja,
        ncolumns: columnas a importar,
        convert: cambiar tipos de datos de columnas
    """
    df = pd.read_excel(
                       dir, 
                       sheet_name=sheet, 
                       na_values=['(en blanco)'],
                       header=0,usecols=ncolumns,
                       converters= convert
                      )
    df = pd.DataFrame(df)
    return df

def info_picos(df, finca=None, cosecha=None, bloque=None, nvariedad=None, pico=None):
    """
        
    """
    # Filtrar el DataFrame según los valores opcionales de cosecha, finca, flor, bloque y nvariedad
    if cosecha is not None:
        df = df[df['cosecha'] == cosecha]
    if finca is not None:
        df = df[df['finca'] == finca]
    if bloque is not None:
        df = df[df['bloque'] == bloque]
    if nvariedad is not None:
        df = df[df['nvariedad'] == nvariedad]
    if pico is not None:
        df = df[df['pico'] == pico]
        

    df = df.reset_index(drop=True)
    
    if pico==1:
        s = 3
    else:
        s = 9
        
    ncol = df.shape[1] - 4
    largo = len(df)
    
     # Calcular las cuatro semanas continuas con la producción más alta en las columnas 'PT' y 'RE'
    for col in ['f_m']:
        tallos = np.array(df[col])
        t_lista = 0
        i_final = 0
        for i in range(largo):
                lista = list(tallos[i:i + s + 1])
                res = np.sum(lista)
                if res > t_lista:
                    t_lista = res
                    i_final = i + s
        
        #suma 4 curvas altas
        sum_altas = np.sum(tallos[i_final - s: i_final + 1])
            
        curva = tallos[i_final - s: i_final + 1]
                
        # Establecer la etiqueta 'sem_pico' en la última semana de las cuatro semanas de producción más alta

        df.loc[df.index[i_final], 'sem_pico'] = df.iloc[i_final,ncol]
        df.loc[df.index[i_final], 'sum_altas' ] = sum_altas
    
    return df.fillna(0)

def analisis_picos(df):
    # Agrupar el DataFrame por finca, cosecha, bloque y nvariedad y aplicar la función info_vitrinas en cada grupo
    groups = df.groupby(['finca', 'cosecha', 'bloque', 'nvariedad','pico'])
    new_df = pd.DataFrame()
    
    for name, group in groups:
        try:
            new_group = info_picos(df, *name)
            new_df = pd.concat([new_df, new_group], ignore_index=True)
        except:
            pass
    
    return new_df[new_df.sem_pico>0]

# Define una función para aplicar la lógica a cada fila
"""def calcular_filtro(row):
    if row['filtro'] == 1 and abs(row['sem_pico_x'] - row['sem_pico_y']) < (3 if row['pico'] > 1 else 2):
        return 2
    else:
        return row['filtro']"""
    
def calcular_filtro(row):
    if row['filtro'] == 1:
        if row['pico'] == 1 and abs(row['sem_pico_x'] - row['sem_pico_y']) < 3:
            return 2
        elif row['pico'] == 2 and abs(row['sem_pico_x'] - row['sem_pico_y']) < 10:
            return 2
        elif row['pico'] == 3: #and abs(row['sem_pico_x'] - row['sem_pico_y']) < 4:
            return 2
        else:
            return 1

def coloca_pico(edad):
    if edad<=35:
        return 1
    elif edad>=36 and edad<=68:
        return 2
    else:
        return 3
    
def procesar_curva(dframe, finca, vari):
    """
    Process curve for specific finca and variety
    
    Args:
        dframe (pd.DataFrame): Input dataframe
        finca (str): Farm identifier
        vari (str): Variety name
    
    Returns:
        pd.DataFrame: DataFrame with added columns fm_suave and ciclo
    """
    # Filter dataframe
    df = dframe.copy()
    df = df[(df.nvariedad == vari) & (df.finca == finca)]
    
    if df.empty:
        print(f"No data found for finca: {finca}, variety: {vari}")
        return df
    
    # Get curve data
    y = curve_ini(df)
    curve = np.array(y)
    
    # Apply curve smoothing - call function only once
    result, i_final, nresult = datos_curva(curve)
    
    # Ensure we have the right length for the dataframe
    if len(nresult) != len(df):
        # Trim or pad to match dataframe length
        if len(nresult) > len(df):
            nresult = nresult[:len(df)]
        else:
            # Pad with zeros if needed
            nresult = np.pad(nresult, (0, len(df) - len(nresult)), 'constant')
    
    # Add new columns to dataframe
    df['fm_suave'] = nresult
    df['ciclo'] = i_final + EDAD_INI
    
    return df

# Example usage function
def procesar_todas_curvas(dframe):
    """
    Process curves for all finca-variety combinations
    
    Args:
        dframe (pd.DataFrame): Input dataframe
    
    Returns:
        pd.DataFrame: Complete dataframe with processed curves
    """
    resultados = []
    
    # Get unique combinations of finca and variety
    combinations = dframe[['finca', 'nvariedad']].drop_duplicates()
    
    for _, row in combinations.iterrows():
        finca = row['finca']
        variedad = row['nvariedad']
        
        try:
            df_procesado = procesar_curva(dframe, finca, variedad)
            if not df_procesado.empty:
                resultados.append(df_procesado)
        except Exception as e:
            print(f"Error processing finca {finca}, variety {variedad}: {e}")
    
    if resultados:
        return pd.concat(resultados, ignore_index=True)
    else:
        return dframe
    
def procesar_curva(dframe, finca, vari):
    """
    Process curve for specific finca and variety
    
    Args:
        dframe (pd.DataFrame): Input dataframe
        finca (str): Farm identifier
        vari (str): Variety name
    
    Returns:
        pd.DataFrame: DataFrame with added columns fm_suave and ciclo
    """
    # Filter dataframe
    df = dframe.copy()
    df = df[(df.nvariedad == vari) & (df.finca == finca)]
    
    if df.empty:
        print(f"No data found for finca: {finca}, variety: {vari}")
        return df
    
    # Get curve data
    y = curve_ini(df)
    curve = np.array(y)
    
    # Apply curve smoothing - call function only once
    result, i_final, nresult = datos_curva(curve)
    
    # Ensure we have the right length for the dataframe
    if len(nresult) != len(df):
        # Trim or pad to match dataframe length
        if len(nresult) > len(df):
            nresult = nresult[:len(df)]
        else:
            # Pad with zeros if needed
            nresult = np.pad(nresult, (0, len(df) - len(nresult)), 'constant')
    
    # Add new columns to dataframe
    df['fm_suave'] = nresult
    df['ciclo'] = i_final + EDAD_INI
    
    return df

# Example usage function
def procesar_todas_curvas(dframe):
    """
    Process curves for all finca-variety combinations
    
    Args:
        dframe (pd.DataFrame): Input dataframe
    
    Returns:
        pd.DataFrame: Complete dataframe with processed curves
    """
    resultados = []
    
    # Get unique combinations of finca and variety
    combinations = dframe[['finca', 'nvariedad']].drop_duplicates()
    
    for _, row in combinations.iterrows():
        finca = row['finca']
        variedad = row['nvariedad']
        
        try:
            df_procesado = procesar_curva(dframe, finca, variedad)
            if not df_procesado.empty:
                resultados.append(df_procesado)
        except Exception as e:
            print(f"Error processing finca {finca}, variety {variedad}: {e}")
    
    if resultados:
        return pd.concat(resultados, ignore_index=True)
    else:
        return dframe