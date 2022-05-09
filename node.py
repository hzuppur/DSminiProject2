import socket
import time
import threading
import random

from nodeconnection import NodeConnection

"""
Implementation based of https://github.com/macsnoeren/python-p2p-network
"""


def get_id_as_int(str_id):
    return int(str_id[1:])


class Node(threading.Thread):
    """Implements a node that is able to connect to other nodes and is able to accept connections from other nodes.
    After instantiation, the node creates a TCP/IP server with the given port.
    Create instance of a Node. If you want to implement the Node functionality with a callback, you should
    provide a callback method. It is preferred to implement a new node by extending this Node class.
      host: The host name or ip address that is used to bind the TCP/IP server to.
      port: The port number that is used to bind the TCP/IP server to.
      callback: (optional) The callback that is invokes when events happen inside the network
               def node_callback(event, main_node, connected_node, data):
                 event: The event string that has happened.
                 main_node: The main node that is running all the connections with the other nodes.
                 connected_node: Which connected node caused the event.
                 data: The data that is send by the connected node."""

    def __init__(self, host, port, id=None, callback=None, n=1):
        """Create instance of a Node. If you want to implement the Node functionality with a callback, you should
           provide a callback method. It is preferred to implement a new node by extending this Node class.
            host: The host name or ip address that is used to bind the TCP/IP server to.
            port: The port number that is used to bind the TCP/IP server to.
            id: (optional) This id will be associated with the node. When not given a unique ID will be created.
            callback: (optional) The callback that is invokes when events happen inside the network."""
        super(Node, self).__init__()

        # When this flag is set, the node will stop and close
        self.terminate_flag = threading.Event()

        # Server details, host (or ip) to bind to and the port
        self.host = host
        self.port = port

        # Events are send back to the given callback
        self.callback = callback

        # Nodes that have established a connection with this node
        self.nodes_inbound = []  # Nodes that are connect with us N->(US)

        # Nodes that this nodes is connected to
        self.nodes_outbound = []  # Nodes that we are connected to (US)->N

        # A list of nodes that should be reconnected to whenever the connection was lost
        self.reconnect_to_nodes = []

        self.id = str(id)
        self.state = "NF"
        self.nodes_in_network = n
        self.rank = "secondary"
        self.orders_received = []
        self.majority = None
        self.k = 1
        self.quorum = []
        self.initial_order = None

        # Start the TCP/IP server
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.init_server()

        # Debugging on or off!
        self.debug = False

    @property
    def all_nodes(self):
        """Return a list of all the nodes, inbound and outbound, that are connected with this node."""
        return self.nodes_inbound + self.nodes_outbound

    def debug_print(self, message):
        """When the debug flag is set to True, all debug messages are printed in the console."""
        if self.debug:
            print("DEBUG (" + self.id + "): " + message)

    def init_server(self):
        """Initialization of the TCP/IP server to receive connections. It binds to the given host and port."""
        print("Initialisation of the Node on port: " + str(self.port) + " on node (" + self.id + ")")
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(10.0)
        self.sock.listen(1)

    def print_connections(self):
        """Prints the connection overview of the node. How many inbound and outbound connections have been made."""
        print("Node connection overview:")
        print("- Total nodes connected with us: %d" % len(self.nodes_inbound))
        print("- Total nodes connected to     : %d" % len(self.nodes_outbound))

    def send_to_nodes(self, data, exclude=[]):
        """ Send a message to all the nodes that are connected with this node. data is a python variable which is
            converted to JSON that is send over to the other node. exclude list gives all the nodes to which this
            data should not be sent."""
        for n in self.nodes_inbound:
            if n in exclude:
                self.debug_print("Node send_to_nodes: Excluding node in sending the message")
            else:
                self.send_to_node(n, data)

        for n in self.nodes_outbound:
            if n in exclude:
                self.debug_print("Node send_to_nodes: Excluding node in sending the message")
            else:
                self.send_to_node(n, data)

    def send_to_node(self, n, data):
        """ Send the data to the node n if it exists."""
        if n in self.nodes_inbound or n in self.nodes_outbound:
            n.send(data)
        else:
            self.debug_print("Node send_to_node: Could not send the data, node is not found!")

    def connect_with_node(self, host, port, reconnect=False):
        """ Make a connection with another node that is running on host with port. When the connection is made,
            an event is triggered outbound_node_connected. When the connection is made with the node, it exchanges
            the id's of the node. First we send our id and then we receive the id of the node we are connected to.
            When the connection is made the method outbound_node_connected is invoked. If reconnect is True, the
            node will try to reconnect to the code whenever the node connection was closed. The method returns
            True when the node is connected with the specific host."""

        if host == self.host and port == self.port:
            print("connect_with_node: Cannot connect with yourself!!")
            return False

        # Check if node is already connected with this node!
        for node in self.nodes_outbound:
            if node.host == host and node.port == port:
                print("connect_with_node: Already connected with this node (" + node.id + ").")
                return True

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.debug_print("connecting to %s port %s" % (host, port))
            sock.connect((host, port))

            # Basic information exchange (not secure) of the id's of the nodes!
            sock.send(self.id.encode('utf-8'))  # Send my id to the connected node!
            connected_node_id = sock.recv(4096).decode('utf-8')  # When a node is connected, it sends its id!

            # Cannot connect with yourself
            if self.id == connected_node_id:
                print("connect_with_node: You cannot connect with yourself?!")
                sock.send("CLOSING: Already having a connection together".encode('utf-8'))
                sock.close()
                return True

            # Fix bug: Cannot connect with nodes that are already connected with us!
            #          Send message and close the socket.
            for node in self.nodes_inbound:
                if node.host == host and node.id == connected_node_id:
                    print("connect_with_node: This node (" + node.id + ") is already connected with us.")
                    sock.send("CLOSING: Already having a connection together".encode('utf-8'))
                    sock.close()
                    return True

            thread_client = self.create_new_connection(sock, connected_node_id, host, port)
            thread_client.start()

            self.nodes_outbound.append(thread_client)
            self.outbound_node_connected(thread_client)

            # If reconnection to this host is required, it will be added to the list!
            if reconnect:
                self.debug_print("connect_with_node: Reconnection check is enabled on node " + host + ":" + str(port))
                self.reconnect_to_nodes.append({
                    "host": host, "port": port, "tries": 0
                })

            return True

        except Exception as e:
            self.debug_print("TcpServer.connect_with_node: Could not connect with node. (" + str(e) + ")")
            return False

    def disconnect_with_node(self, node):
        """Disconnect the TCP/IP connection with the specified node. It stops the node and joins the thread.
           The node will be deleted from the nodes_outbound list. Before closing, the method
           node_disconnect_with_outbound_node is invoked."""
        if node in self.nodes_outbound:
            self.node_disconnect_with_outbound_node(node)
            node.stop()

        else:
            self.debug_print(
                "Node disconnect_with_node: cannot disconnect with a node with which we are not connected.")

    def stop(self):
        """Stop this node and terminate all the connected nodes."""
        self.node_request_to_stop()
        self.terminate_flag.set()

    # This method can be overrided when a different nodeconnection is required!
    def create_new_connection(self, connection, id, host, port):
        """When a new connection is made, with a node or a node is connecting with us, this method is used
           to create the actual new connection. The reason for this method is to be able to override the
           connection class if required. In this case a NodeConnection will be instantiated to represent
           the node connection."""
        return NodeConnection(self, connection, id, host, port)

    def reconnect_nodes(self):
        """This method checks whether nodes that have the reconnection status are still connected. If not
           connected these nodes are started again."""
        for node_to_check in self.reconnect_to_nodes:
            found_node = False
            self.debug_print(
                "reconnect_nodes: Checking node " + node_to_check["host"] + ":" + str(node_to_check["port"]))

            for node in self.nodes_outbound:
                if node.host == node_to_check["host"] and node.port == node_to_check["port"]:
                    found_node = True
                    node_to_check["trials"] = 0  # Reset the trials
                    self.debug_print("reconnect_nodes: Node " + node_to_check["host"] + ":" + str(
                        node_to_check["port"]) + " still running!")

            if not found_node:  # Reconnect with node
                node_to_check["trials"] += 1
                if self.node_reconnection_error(node_to_check["host"], node_to_check["port"], node_to_check["trials"]):
                    self.connect_with_node(node_to_check["host"],
                                           node_to_check["port"])  # Perform the actual connection

                else:
                    self.debug_print("reconnect_nodes: Removing node (" + node_to_check["host"] + ":" + str(
                        node_to_check["port"]) + ") from the reconnection list!")
                    self.reconnect_to_nodes.remove(node_to_check)

    def run(self):
        """The main loop of the thread that deals with connections from other nodes on the network. When a
           node is connected it will exchange the node id's. First we receive the id of the connected node
           and secondly we will send our node id to the connected node. When connected the method
           inbound_node_connected is invoked."""
        while not self.terminate_flag.is_set():  # Check whether the thread needs to be closed
            try:
                self.debug_print("Node: Wait for incoming connection")
                connection, client_address = self.sock.accept()

                # Basic information exchange (not secure) of the id's of the nodes!
                connected_node_id = connection.recv(4096).decode('utf-8')
                connection.send(self.id.encode('utf-8'))

                thread_client = self.create_new_connection(
                    connection, connected_node_id, client_address[0], client_address[1])
                thread_client.start()

                self.nodes_inbound.append(thread_client)
                self.inbound_node_connected(thread_client)

            except socket.timeout:
                self.debug_print('Node: Connection timeout!')
            except Exception as e:
                raise e

            self.reconnect_nodes()
            # All nodes have not connected
            time.sleep(0.01)

        # Thread needs to be terminated
        self.close()

    def outbound_node_connected(self, node):
        """This method is invoked when a connection with a outbound node was successfull. The node made
           the connection itself."""
        self.debug_print("outbound_node_connected: " + node.id)
        if self.callback is not None:
            self.callback("outbound_node_connected", self, node, {})

    def inbound_node_connected(self, node):
        """This method is invoked when a node successfully connected with us."""
        self.debug_print("inbound_node_connected: " + node.id)
        if self.callback is not None:
            self.callback("inbound_node_connected", self, node, {})

    def node_disconnected(self, node):
        """While the same nodeconnection class is used, the class itself is not able to
           determine if it is a inbound or outbound connection. This function is making
           sure the correct method is used."""
        self.debug_print("node_disconnected: " + node.id)

        if node in self.nodes_inbound:
            del self.nodes_inbound[self.nodes_inbound.index(node)]
            self.inbound_node_disconnected(node)

        if node in self.nodes_outbound:
            del self.nodes_outbound[self.nodes_outbound.index(node)]
            self.outbound_node_disconnected(node)

    def inbound_node_disconnected(self, node):
        """This method is invoked when a node, that was previously connected with us, is in a disconnected
           state."""
        self.debug_print("inbound_node_disconnected: " + node.id)
        if self.callback is not None:
            self.callback("inbound_node_disconnected", self, node, {})

    def outbound_node_disconnected(self, node):
        """This method is invoked when a node, that we have connected to, is in a disconnected state."""
        self.debug_print("outbound_node_disconnected: " + node.id)
        if self.callback is not None:
            self.callback("outbound_node_disconnected", self, node, {})

    def node_message(self, node, data):
        """This method is invoked when a node send us a message."""
        order_type, order = data.split(":")

        if order_type == "PRIMARY":
            self.orders_received.append(order)
            for node in self.all_nodes:
                if self.state == "NF":
                    self.send_to_node(node, "SECONDARY:" + order)
                else:
                    self.send_to_node(node, "SECONDARY:" + random.choice(["NF", "F"]))
        elif order_type == "SECONDARY":
            self.orders_received.append(order)
            if len(self.orders_received) == len(self.all_nodes):
                voted_attack, voted_retreat = self.count_votes(self.orders_received)

                if len(self.all_nodes) + 1 < 3 * self.k + 1:
                    self.majority = "undefined"
                elif voted_attack > voted_retreat:
                    self.majority = "attack"
                elif voted_retreat > voted_attack:
                    self.majority = "retreat"
                else:
                    self.majority = "undefined"

                print(f"G{self.id}, majority={self.majority}, state={self.state}")

                self.send_to_nodes("RESULT:" + self.majority)

                self.majority = None
                self.orders_received = []
        elif self.rank == "primary" and order_type == "RESULT":
            self.quorum.append(order)

            if len(self.quorum) == len(self.all_nodes):
                voted_attack, voted_retreat = self.count_votes(self.quorum)
                voted_undefined = len(self.all_nodes) - voted_attack - voted_retreat
                self.quorum = []
                if len(self.all_nodes) + 1 >= 3 * self.k + 1:
                    message = f"Execute order: {self.initial_order}! Non-faulty nodes in the system "
                else:
                    message = f"Execute order: cannot be determined – not enough generals in the system! 1 faulty node in the system "

                if voted_attack > voted_retreat:
                    message += f"- {voted_attack} out of {len(self.all_nodes) + 1} quorum suggest attack"
                elif voted_retreat > voted_attack:
                    message += f"- {voted_retreat} out of {len(self.all_nodes) + 1} quorum suggest retreat"
                else:
                    message += f"- {voted_undefined} out of {len(self.all_nodes) + 1} quorum not consistent"

                print(message)

    def node_disconnect_with_outbound_node(self, node):
        """This method is invoked just before the connection is closed with the outbound node. From the node
           this request is created."""
        self.debug_print("node wants to disconnect with oher outbound node: " + node.id)
        if self.callback is not None:
            self.callback("node_disconnect_with_outbound_node", self, node, {})

    def node_request_to_stop(self):
        """This method is invoked just before we will stop. A request has been given to stop the node and close
           all the node connections. It could be used to say goodbey to everyone."""
        self.debug_print("node is requested to stop!")
        if self.callback is not None:
            self.callback("node_request_to_stop", self, {}, {})

    def node_reconnection_error(self, host, port, trials):
        """This method is invoked when a reconnection error occurred. The node connection is disconnected and the
           flag for reconnection is set to True for this node. This function can be overidden to implement your
           specific logic to take action when a lot of trials have been done. If the method returns True, the
           node will try to perform the reconnection. If the method returns False, the node will stop reconnecting
           to this node. The node will forever tries to perform the reconnection."""
        self.debug_print("node_reconnection_error: Reconnecting to node " + host + ":" + str(port) + " (trials: " + str(
            trials) + ")")
        return True

    def __str__(self):
        return f"G{self.id}, {self.rank}, state={self.state}"

    def __repr__(self):
        return '<Node {}:{} id: {}>'.format(self.host, self.port, self.id)

    def close(self):
        print("Node stopping...")
        for t in self.nodes_inbound:
            t.stop()

        for t in self.nodes_outbound:
            t.stop()

        time.sleep(1)

        for t in self.nodes_inbound:
            t.join()

        for t in self.nodes_outbound:
            t.join()

        self.sock.settimeout(None)
        self.sock.close()
        print("Node stopped")

    def count_votes(self, votes):
        voted_attack = 0
        voted_retreat = 0

        for vote in votes:
            if vote == "attack":
                voted_attack += 1
            elif vote == "retreat":
                voted_retreat += 1

        return voted_attack, voted_retreat

    def send_order(self, order):
        self.initial_order = order
        for node in self.all_nodes:
            if self.state == "NF":
                self.send_to_node(node, "PRIMARY:" + order)
            else:
                self.send_to_node(node, "PRIMARY:" + random.choice(["NF", "F"]))
