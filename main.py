#!/usr/bin/python

import sys
import time
from node import Node


def get_general(nodes):
    for node in nodes:
        if node.rank == "primary":
            return node


def start(n=2):
    nodes = []
    n_id = 1
    port = 8001
    host = "127.0.0.1"

    # Create the nodes
    for i in range(n):
        node = Node(host, port, id=n_id, n=n)
        if i == 1:
            node.rank = "primary"
        n_id += 1
        port += 1
        node.start()
        nodes.append(node)

    # Connect the nodes
    for i in range(len(nodes)):
        node = nodes[i]
        for j in range(i + 1, len(nodes)):
            other_node = nodes[j]
            node.connect_with_node(host, other_node.port)

    print("Available commands:")
    print("\t* actual-order ORDER - Valid values for ORDER are 'attack' or 'retreat'")
    print("\t* g-state - Shows the list of generals and along with their respective state and role")
    print("\t* g-state ID STATE - where ID is the general ID and STATE is either 'faulty' or 'non-faulty'")
    print("\t* g-kill ID - this commands remove a general based on its ID")
    print("\t* g-add K, where K is the number of new generals")

    print("\t* q - Quit")
    while True:
        user_input = input("Enter command, press q to exit: \n").split(" ")
        command = user_input[0]
        command_params = user_input[1:] if len(user_input) > 1 else []

        if command == "actual-order":
            general_node = get_general(nodes)
            order = command_params[0]
            if order not in ["attack", "retreat"]:
                print(f"Invalid value {order}, valid valuse are attack and retreat")
            general_node.send_order(order)
        elif command == "g-state":
            if len(command_params) == 0:
                for node in nodes:
                    print(node)
            else:
                node_id, node_state = command_params[0], command_params[1]
                if node_state not in ["faulty", "non-faulty"]:
                    print(f"Invalid value {node_state}, vald values are F and NF")
                for node in nodes:
                    if node.id == node_id:
                        if node_state == "faulty":
                            node.state = "F"
                        elif node_state == "non-faulty":
                            node.state = "NF"
                        break
        elif command == "g-kill":
            node_id = command_params[0]
            for node in nodes:
                if node.id == node_id:
                    nodes.remove(node)

                    for other_node in nodes:
                        for in_port in other_node.nodes_inbound:
                            if in_port.id == node.id:
                                other_node.nodes_inbound.remove(in_port)
                        for out_port in other_node.nodes_outbound:
                            if out_port.id == node.id:
                                other_node.nodes_outbound.remove(out_port)

                    node.stop()
                    if node.rank == "primary":
                        nodes[0].rank = "primary"
                break
            time.sleep(14)
        elif command == "g-add":
            new_nodes = int(command_params[0])
            new_node_list = []
            # Create the nodes
            for i in range(new_nodes):
                node = Node(host, port, id=n_id, n=n)
                n_id += 1
                port += 1
                node.start()
                new_node_list.append(node)

            for i in range(len(new_node_list)):
                node = new_node_list[i]
                for j in range(i + 1, len(new_node_list)):
                    other_node = new_node_list[j]
                    node.connect_with_node(host, other_node.port)

            for old_node in nodes:
                for new_node in new_node_list:
                    old_node.connect_with_node(host, new_node.port)
            nodes.extend(new_node_list)
        elif command == "q":
            break
        else:
            print("Unknown command")
        time.sleep(0.5)

    for node in nodes:
        node.stop()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        start(int(sys.argv[1]))
    else:
        raise ValueError("Need to specifify n")
