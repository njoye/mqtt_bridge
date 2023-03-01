import inject
import paho.mqtt.client as mqtt
import rospy

from .bridge import create_bridge
from .mqtt_client import create_private_path_extractor
from .util import lookup_object

is_connected = False

def create_config(mqtt_client, serializer, deserializer, mqtt_private_path):
    if isinstance(serializer, str):
        serializer = lookup_object(serializer)
    if isinstance(deserializer, str):
        deserializer = lookup_object(deserializer)
    private_path_extractor = create_private_path_extractor(mqtt_private_path)
    def config(binder):
        binder.bind('serializer', serializer)
        binder.bind('deserializer', deserializer)
        binder.bind(mqtt.Client, mqtt_client)
        binder.bind('mqtt_private_path_extractor', private_path_extractor)
    return config


def mqtt_bridge_node():
    # init node
    rospy.init_node('mqtt_bridge_node')

    # load parameters
    params = rospy.get_param("~", {})
    mqtt_params = params.pop("mqtt", {})
    conn_params = mqtt_params.pop("connection")
    mqtt_private_path = mqtt_params.pop("private_path", "")
    bridge_params = params.get("bridge", [])

    # set state param
    rospy.set_param('mqttbridge/is_connected', False)    


    # create mqtt client
    mqtt_client_factory_name = rospy.get_param(
        "~mqtt_client_factory", ".mqtt_client:default_mqtt_client_factory")
    mqtt_client_factory = lookup_object(mqtt_client_factory_name)
    mqtt_client = mqtt_client_factory(mqtt_params)

    # load serializer and deserializer
    serializer = params.get('serializer', 'msgpack:dumps')
    deserializer = params.get('deserializer', 'msgpack:loads')

    # dependency injection
    config = create_config(
        mqtt_client, serializer, deserializer, mqtt_private_path)
    inject.configure(config)

    # configure and connect to MQTT broker
    mqtt_client.on_connect = _on_connect
    mqtt_client.on_disconnect = _on_disconnect
    
    is_connected = False
    while not is_connected:
        try:
            mqtt_client.connect(**conn_params)
            is_connected = True
        except:
            rospy.logerr("Couldn't connect to broker during start sequence, trying again.")
            rospy.sleep(rospy.Duration(1))

    # configure bridges
    bridges = []
    for bridge_args in bridge_params:
        bridges.append(create_bridge(**bridge_args))

    # start MQTT loop
    mqtt_client.loop_start()

    # register shutdown callback and spin
    rospy.on_shutdown(mqtt_client.disconnect)
    rospy.on_shutdown(mqtt_client.loop_stop)

    rospy.spin()


def _on_connect(client, userdata, flags, response_code):
    rospy.loginfo('MQTT connected')
    rospy.set_param("mqttbridge/is_connected", True)


def _on_disconnect(client, userdata, response_code):
    rospy.loginfo('MQTT disconnected')

    params = rospy.get_param("~", {})
    mqtt_params = params.pop("mqtt", {})
    conn_params = mqtt_params.pop("connection")

    rospy.set_param("mqttbridge/is_connected", False)

    while not rospy.get_param("mqttbridge/is_connected") and not rospy.is_shutdown():
        rospy.loginfo(f"Trying to reconnect to broker with params {conn_params}")
        try:
            rospy.sleep(rospy.Duration(1))
            client.connect(**conn_params)
            rospy.set_param('mqttbridge/is_connected', True)
        except:    
            rospy.logerr("Couldn't connect to the broker")
            rospy.set_param('mqttbridge/is_connected', False)


__all__ = ['mqtt_bridge_node']
