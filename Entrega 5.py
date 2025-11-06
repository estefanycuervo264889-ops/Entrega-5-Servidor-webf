# main_esp32_thingspeak_comandos.py - CON COMANDOS WEB, LEDs Y TONOS DIFERENTES
import network
import urequests
import time
import dht
from machine import Pin, PWM
import json
import gc

# Configuración
SENSOR_PIN = 4
BOTON_PANICO_PIN = 26
ZUMBADOR_PIN = 25
LED_ALARMA_PIN = 2      # LED amarillo para alarma activa
LED_WIFI_PIN = 5        # LED multi para conexión WiFi

RED_NOMBRE = "Gugu"
RED_CLAVE = "wi123456"

TELEGRAM_TOKEN = "7959030953:AAF2kR3TeijNUrkIY6ut8raB-R0V6a8NWaU"
TELEGRAM_CHAT = "7618570704"

# ThingSpeak Config 
THINGSPEAK_API_KEY = "JI002XYUG7JNG3VE"
THINGSPEAK_CHANNEL_ID = "3148282"  
THINGSPEAK_URL = "https://api.thingspeak.com/update"
THINGSPEAK_READ_URL = "https://api.thingspeak.com/channels/{}/feeds.json".format(THINGSPEAK_CHANNEL_ID)

# Intervalos
TIEMPO_MEDICION = 30
TIEMPO_REVISION_TELEGRAM = 5
TIEMPO_REVISION_COMANDOS = 10  # Revisar comandos cada 10 segundos

# Variables globales
temperatura_actual = 0.0
humedad_actual = 0.0
limite_temperatura = 30.0
limite_humedad = 70.0
aviso_temperatura = False
aviso_humedad = False
alerta_activa = False
panico_activado = False
alarma_desactivada = False
ultimo_id_recibido = 0
ultimo_comando_id = 0  # Para trackear comandos de ThingSpeak

# Estados de alarma anteriores (para detectar cambios)
aviso_temperatura_anterior = False
aviso_humedad_anterior = False
panico_activado_anterior = False

# Hardware
medidor = dht.DHT11(Pin(SENSOR_PIN))
boton_panico = Pin(BOTON_PANICO_PIN, Pin.IN, Pin.PULL_UP)
zumbador = PWM(Pin(ZUMBADOR_PIN))  # Cambiado a PWM para control de tono
led_alarma = Pin(LED_ALARMA_PIN, Pin.OUT)
led_wifi = Pin(LED_WIFI_PIN, Pin.OUT)

# Inicializar periféricos
zumbador.duty(0)  # Apagar zumbador inicialmente
led_alarma.off()
led_wifi.off()

# Configuración de tonos (frecuencias en Hz)
TONO_TEMPERATURA = 1000   # Tono agudo para temperatura
TONO_HUMEDAD = 500        # Tono medio para humedad
TONO_COMBINADO = 1500     # Tono muy agudo para ambas
TONO_PANICO = 800         # Tono intermitente para pánico

# Funciones de tonos de alarma
def tono_temperatura():
    """Tono específico para alarma de temperatura (rápido y agudo)"""
    for i in range(3):
        zumbador.freq(TONO_TEMPERATURA)
        zumbador.duty(512)  # 50% duty cycle
        time.sleep(0.2)
        zumbador.duty(0)
        time.sleep(0.1)

def tono_humedad():
    """Tono específico para alarma de humedad (lento y grave)"""
    for i in range(2):
        zumbador.freq(TONO_HUMEDAD)
        zumbador.duty(512)
        time.sleep(0.4)
        zumbador.duty(0)
        time.sleep(0.2)

def tono_combinado():
    """Tono específico para ambas alarmas activas (alternante)"""
    for i in range(4):
        zumbador.freq(TONO_COMBINADO if i % 2 == 0 else TONO_HUMEDAD)
        zumbador.duty(512)
        time.sleep(0.15)
        zumbador.duty(0)
        time.sleep(0.05)

def tono_panico():
    """Tono específico para pánico (intermitente rápido)"""
    zumbador.freq(TONO_PANICO)
    zumbador.duty(512)
    time.sleep(0.1)
    zumbador.duty(0)
    time.sleep(0.1)

def apagar_alarma():
    """Apagar completamente el zumbador"""
    zumbador.duty(0)

def controlar_alarma_sonora():
    """Controlar la alarma sonora según el tipo de alerta"""
    global aviso_temperatura_anterior, aviso_humedad_anterior, panico_activado_anterior
    
    # Solo activar si hay alerta y no está desactivada
    if alerta_activa and not alarma_desactivada:
        
        # Detectar cambio de estado para reproducir tono
        estado_cambiado = (aviso_temperatura != aviso_temperatura_anterior or 
                          aviso_humedad != aviso_humedad_anterior or 
                          panico_activado != panico_activado_anterior)
        
        # Reproducir tono según el tipo de alarma (solo si cambió el estado o es pánico)
        if estado_cambiado or panico_activado:
            if panico_activado:
                tono_panico()
            elif aviso_temperatura and aviso_humedad:
                tono_combinado()
            elif aviso_temperatura:
                tono_temperatura()
            elif aviso_humedad:
                tono_humedad()
        
        # Actualizar estados anteriores
        aviso_temperatura_anterior = aviso_temperatura
        aviso_humedad_anterior = aviso_humedad
        panico_activado_anterior = panico_activado
        
    else:
        # Apagar alarma si no hay alerta o está desactivada
        apagar_alarma()
        # Resetear estados anteriores cuando se apaga la alarma
        aviso_temperatura_anterior = False
        aviso_humedad_anterior = False
        panico_activado_anterior = False

# Funciones auxiliares (las mismas que antes, pero actualizadas para usar PWM)
def conectar_red(timeout_s=20):
    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)
    
    # Encender LED WiFi mientras intenta conectar
    led_wifi.on()
    
    if wifi.isconnected():
        print("WiFi ya conectado")
        return wifi.ifconfig()[0]
        
    print("Conectando WiFi...")
    wifi.connect(RED_NOMBRE, RED_CLAVE)
    inicio = time.time()
    
    while not wifi.isconnected():
        # Parpadeo rápido del LED WiFi durante conexión
        led_wifi.value(not led_wifi.value())
        time.sleep(0.3)
        if time.time() - inicio > timeout_s:
            break
            
    if wifi.isconnected():
        direccion_ip = wifi.ifconfig()[0]
        print("WiFi OK:", direccion_ip)
        # LED WiFi encendido fijo cuando está conectado
        led_wifi.on()
        return direccion_ip
    else:
        print("No WiFi")
        # LED WiFi apagado si no hay conexión
        led_wifi.off()
        return None

def actualizar_led_alarma():
    """Actualizar el LED de alarma según el estado del sistema"""
    if panico_activado:
        # Parpadeo rápido para pánico
        led_alarma.value(not led_alarma.value())
    elif alerta_activa and not alarma_desactivada:
        # Parpadeo lento para alerta normal
        if time.ticks_ms() % 1000 < 500:  # 500ms encendido, 500ms apagado
            led_alarma.on()
        else:
            led_alarma.off()
    else:
        # Apagado si no hay alerta
        led_alarma.off()

def enviar_mensaje_telegram(texto):
    try:
        url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN)
        datos = {"chat_id": TELEGRAM_CHAT, "text": texto}
        respuesta = urequests.post(url, json=datos, timeout=5)
        respuesta.close()
        print("TG:", texto[:30] + "..." if len(texto) > 30 else texto)
    except Exception as error:
        print("Error TG:", error)

def enviar_thingspeak(temp, hum, panico=False, silencio=False):
    """Enviar datos a ThingSpeak con estados adicionales"""
    try:
        # field1: Temperatura, field2: Humedad
        # field3: Estado Pánico (1=activado, 0=normal)
        # field4: Estado Silencio (1=silenciado, 0=normal)
        estado_panico = 1 if panico else 0
        estado_silencio = 1 if silencio else 0
        
        url = "{}?api_key={}&field1={:.1f}&field2={:.1f}&field3={}&field4={}".format(
            THINGSPEAK_URL, 
            THINGSPEAK_API_KEY, 
            temp, 
            hum,
            estado_panico,
            estado_silencio
        )
        
        print("Enviando a ThingSpeak: {:.1f}°C, {:.1f}%, Panico:{}, Silencio:{}".format(
            temp, hum, estado_panico, estado_silencio))
        
        respuesta = urequests.get(url, timeout=10)
        
        if respuesta.status_code == 200:
            entrada_id = respuesta.text
            if entrada_id != "0":
                print("ThingSpeak OK - ID:", entrada_id)
                respuesta.close()
                return True
            else:
                print("ThingSpeak Error - ID 0")
        else:
            print("Error HTTP ThingSpeak:", respuesta.status_code)
        
        respuesta.close()
        return False
        
    except Exception as error:
        print("Error ThingSpeak:", error)
        return False

def leer_comandos_thingspeak():
    """Leer comandos desde ThingSpeak (usando field5 como campo de comandos)"""
    global panico_activado, alarma_desactivada, ultimo_comando_id
    
    try:
        # Leer los últimos datos para ver si hay comandos nuevos
        url = "{}?api_key={}&results=2".format(THINGSPEAK_READ_URL, THINGSPEAK_API_KEY)
        
        respuesta = urequests.get(url, timeout=10)
        datos = respuesta.json()
        respuesta.close()
        
        if "feeds" in datos and len(datos["feeds"]) > 0:
            # Tomar el dato más reciente
            ultimo_feed = datos["feeds"][0]
            comando_actual = ultimo_feed.get("entry_id", 0)
            
            # Si es un comando nuevo
            if comando_actual > ultimo_comando_id:
                ultimo_comando_id = comando_actual
                
                # Verificar field5 para comandos (1=pánico, 2=silencio, 0=normal)
                campo_comando = ultimo_feed.get("field5", "0")
                
                if campo_comando == "1":  # Comando de pánico
                    print("📱 Comando de PÁNICO recibido desde dashboard")
                    panico_activado = True
                    alarma_desactivada = False
                    enviar_mensaje_telegram("🚨 PÁNICO activado desde Dashboard Web")
                    return "panico"
                    
                elif campo_comando == "2":  # Comando de silencio
                    print("📱 Comando de SILENCIO recibido desde dashboard")
                    alarma_desactivada = True
                    panico_activado = False
                    apagar_alarma()
                    enviar_mensaje_telegram("🔇 Alarma silenciada desde Dashboard Web")
                    return "silencio"
                    
                elif campo_comando == "0":  # Comando de normalidad
                    print("📱 Comando de NORMALIDAD recibido desde dashboard")
                    panico_activado = False
                    alarma_desactivada = False
                    apagar_alarma()
                    return "normal"
        
        return None
        
    except Exception as error:
        print("Error leyendo comandos:", error)
        return None

def guardar_configuracion():
    try:
        config = {
            "limite_temperatura": limite_temperatura,
            "limite_humedad": limite_humedad
        }
        with open("config.json", "w") as f:
            json.dump(config, f)
        print("Config guardada")
    except Exception as e:
        print("Error guardando config:", e)

def cargar_configuracion():
    global limite_temperatura, limite_humedad
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
            limite_temperatura = config.get("limite_temperatura", 30.0)
            limite_humedad = config.get("limite_humedad", 70.0)
        print("Config cargada: Temp={}, Hum={}".format(limite_temperatura, limite_humedad))
    except:
        print("Config por defecto")
        limite_temperatura = 30.0
        limite_humedad = 70.0

def procesar_comandos_telegram():
    global ultimo_id_recibido, limite_temperatura, limite_humedad, panico_activado, alarma_desactivada
    try:
        url = "https://api.telegram.org/bot{}/getUpdates?offset={}".format(TELEGRAM_TOKEN, ultimo_id_recibido + 1)
        respuesta = urequests.get(url, timeout=5)
        datos = respuesta.json()
        respuesta.close()
        if "result" in datos:
            for elemento in datos["result"]:
                ultimo_id_recibido = elemento.get("update_id", ultimo_id_recibido)
                mensaje = elemento.get("message", {})
                texto = mensaje.get("text", "")
                if not texto:
                    continue
                texto = texto.strip()
                print("TG cmd:", texto)
                
                if texto.startswith("/temp"):
                    partes = texto.split()
                    if len(partes) >= 2:
                        try:
                            valor = float(partes[1])
                            if 0 < valor < 100:
                                limite_temperatura = valor
                                guardar_configuracion()
                                enviar_mensaje_telegram("✅ Temp: {:.1f}°C".format(limite_temperatura))
                        except:
                            pass
                
                elif texto.startswith("/hum"):
                    partes = texto.split()
                    if len(partes) >= 2:
                        try:
                            valor = float(partes[1])
                            if 0 <= valor < 100:
                                limite_humedad = valor
                                guardar_configuracion()
                                enviar_mensaje_telegram("✅ Hum: {:.1f}%".format(limite_humedad))
                        except:
                            pass
                
                elif texto == "/estado":
                    estado_temp = "🔴 ALTA" if aviso_temperatura else "✅ Normal"
                    estado_hum = "🔴 ALTA" if aviso_humedad else "✅ Normal"
                    estado_panico = "🚨 ACTIVO" if panico_activado else "✅ Normal"
                    estado_silencio = "🔇 ACTIVO" if alarma_desactivada else "🔊 Normal"
                    
                    # Información de tonos de alarma
                    tipo_alarma = "Ninguna"
                    if panico_activado:
                        tipo_alarma = "🚨 Pánico (tono intermitente)"
                    elif aviso_temperatura and aviso_humedad:
                        tipo_alarma = "🌡️💧 Combinada (tono alternante)"
                    elif aviso_temperatura:
                        tipo_alarma = "🌡️ Temperatura (tono agudo)"
                    elif aviso_humedad:
                        tipo_alarma = "💧 Humedad (tono grave)"
                    
                    enviar_mensaje_telegram(
                        "📊 Estado:\n🌡️ {:.1f}°C ({})\n💧 {:.1f}% ({})\n🚨 Pánico: {}\n🔇 Silencio: {}\n🔊 Tipo Alarma: {}".format(
                            temperatura_actual, estado_temp, humedad_actual, estado_hum, 
                            estado_panico, estado_silencio, tipo_alarma
                        )
                    )
                
                elif texto == "/silence":
                    alarma_desactivada = True
                    panico_activado = False
                    apagar_alarma()
                    enviar_mensaje_telegram("🔇 Silenciado - Alarmas desactivadas")
                
                elif texto == "/panic":
                    panico_activado = True
                    alarma_desactivada = False
                    enviar_mensaje_telegram("🚨 PÁNICO - Tono de emergencia activado")
                    
                elif texto == "/normal":
                    panico_activado = False
                    alarma_desactivada = False
                    apagar_alarma()
                    enviar_mensaje_telegram("✅ Modo normal - Sistema reestablecido")
                    
    except Exception as error:
        print("Error procesando TG:", error)

def leer_sensor():
    """Leer sensor con manejo de errores mejorado"""
    global temperatura_actual, humedad_actual
    try:
        medidor.measure()
        temp = float(medidor.temperature())
        hum = float(medidor.humidity())
        temperatura_actual = temp
        humedad_actual = hum
        print("Sensor: {:.1f}°C, {:.1f}%".format(temp, hum))
        return temp, hum, True
    except Exception as e:
        print("Error leyendo sensor:", e)
        return 0, 0, False

# Arranque principal MODIFICADO con control de tonos
def main():
    global temperatura_actual, humedad_actual, aviso_temperatura, aviso_humedad
    global alerta_activa, panico_activado, alarma_desactivada
    
    print("Iniciando sistema con ThingSpeak, comandos web, LEDs y tonos diferenciados...")
    cargar_configuracion()
    
    # Test inicial de LEDs y buzzer
    print("Testeando periféricos...")
    led_alarma.on()
    led_wifi.on()
    
    # Test de tonos
    print("Testeando tonos de alarma...")
    time.sleep(0.5)
    tono_temperatura()
    time.sleep(0.5)
    tono_humedad()
    time.sleep(0.5)
    tono_combinado()
    time.sleep(0.5)
    tono_panico()
    
    led_alarma.off()
    led_wifi.off()
    time.sleep(0.5)
    
    ip = conectar_red()
    if not ip:
        print("No WiFi - STOP")
        # LED WiFi permanece apagado
        return
    
    # Notificación inicial
    try:
        enviar_mensaje_telegram("🚀 Sistema con tonos diferenciados iniciado - Tono🌡️, Tono💧, Tono🌡️💧, Tono🚨")
    except:
        print("Error enviando mensaje inicial")
    
    # Timing
    ultima_lectura = time.ticks_ms()
    ultima_revision_telegram = time.ticks_ms()
    ultimo_envio_thingspeak = time.ticks_ms()
    ultima_revision_comandos = time.ticks_ms()
    ultimo_parpadeo_led = time.ticks_ms()
    ultimo_control_alarma = time.ticks_ms()
    
    print("Sistema iniciado correctamente - Tonos diferenciados activos")
    print("Tono🌡️: Rápido/agudo | Tono💧: Lento/grave | Tono🌡️💧: Alternante | Tono🚨: Intermitente")
    
    while True:
        try:
            gc.collect()
            
            # Actualizar LED de alarma (cada 100ms para parpadeo suave)
            if time.ticks_diff(time.ticks_ms(), ultimo_parpadeo_led) >= 100:
                ultimo_parpadeo_led = time.ticks_ms()
                actualizar_led_alarma()
            
            # Controlar alarma sonora (cada 500ms)
            if time.ticks_diff(time.ticks_ms(), ultimo_control_alarma) >= 500:
                ultimo_control_alarma = time.ticks_ms()
                controlar_alarma_sonora()
            
            # Botón pánico físico
            if boton_panico.value() == 0 and not panico_activado:
                print("Botón pánico presionado")
                panico_activado = True
                alarma_desactivada = False
                try:
                    enviar_mensaje_telegram("🚨 PÁNICO Físico activado - Tono de emergencia")
                except:
                    pass
                time.sleep(0.5)
            
            # Comandos Telegram
            if time.ticks_diff(time.ticks_ms(), ultima_revision_telegram) >= (TIEMPO_REVISION_TELEGRAM * 1000):
                ultima_revision_telegram = time.ticks_ms()
                procesar_comandos_telegram()
            
            # Comandos desde Dashboard Web (cada 10 segundos)
            if time.ticks_diff(time.ticks_ms(), ultima_revision_comandos) >= (TIEMPO_REVISION_COMANDOS * 1000):
                ultima_revision_comandos = time.ticks_ms()
                comando = leer_comandos_thingspeak()
                if comando:
                    print("✅ Comando web procesado:", comando)
            
            # Lecturas del sensor y envío a ThingSpeak
            tiempo_actual = time.ticks_ms()
            if time.ticks_diff(tiempo_actual, ultima_lectura) >= (TIEMPO_MEDICION * 1000):
                ultima_lectura = tiempo_actual
                print("Leyendo sensor...")
                temp, hum, exito = leer_sensor()
                
                if exito:
                    print("Sensor leído: {:.1f}°C, {:.1f}%".format(temp, hum))
                    
                    # Actualizar banderas de alerta
                    aviso_temperatura = (temp > limite_temperatura)
                    aviso_humedad = (hum > limite_humedad)
                    alerta_activa = aviso_temperatura or aviso_humedad or panico_activado
                    
                    print("Alertas - Temp: {}, Hum: {}, Activa: {}, Panico: {}, Silencio: {}".format(
                        aviso_temperatura, aviso_humedad, alerta_activa, panico_activado, alarma_desactivada))
                    
                    # Información del tipo de alarma sonora
                    if alerta_activa and not alarma_desactivada:
                        if panico_activado:
                            print("🔊 Tono activo: Pánico (intermitente)")
                        elif aviso_temperatura and aviso_humedad:
                            print("🔊 Tono activo: Combinado (alternante)")
                        elif aviso_temperatura:
                            print("🔊 Tono activo: Temperatura (rápido/agudo)")
                        elif aviso_humedad:
                            print("🔊 Tono activo: Humedad (lento/grave)")
                    
                    # Enviar a ThingSpeak (cada 30 segundos mínimo)
                    if time.ticks_diff(tiempo_actual, ultimo_envio_thingspeak) >= 30000:
                        if enviar_thingspeak(temp, hum, panico_activado, alarma_desactivada):
                            ultimo_envio_thingspeak = tiempo_actual
                            print("✅ Datos enviados a ThingSpeak")
                        else:
                            print("❌ Falló envío a ThingSpeak, reintentando en 30s")
                    
                    # Enviar alerta si es necesario
                    if (aviso_temperatura or aviso_humedad) and not alarma_desactivada and not panico_activado:
                        try:
                            if aviso_temperatura and aviso_humedad:
                                estado = "🌡️💧 CRÍTICO - Tono combinado activado"
                            elif aviso_temperatura:
                                estado = "🌡️ ALTA - Tono temperatura activado"
                            elif aviso_humedad:
                                estado = "💧 ALTA - Tono humedad activado"
                                
                            enviar_mensaje_telegram(
                                "⚠️ {:.1f}°C, {:.1f}% - {}".format(temp, hum, estado)
                            )
                            print("Alerta enviada a Telegram")
                        except Exception as tg_error:
                            print("Error enviando alerta TG:", tg_error)
                else:
                    print("Error en lectura del sensor")
            
            time.sleep(0.05)  # Reducido para mejor respuesta del LED y tonos
            
        except Exception as error_principal:
            print("=" * 50)
            print("ERROR EN LOOP PRINCIPAL:")
            print("Tipo:", type(error_principal).__name__)
            print("Mensaje:", error_principal)
            print("=" * 50)
            # Apagar LEDs y alarma en caso de error
            led_alarma.off()
            led_wifi.off()
            apagar_alarma()
            time.sleep(2)

# Ejecutar main
if __name__ == "__main__":
    main()