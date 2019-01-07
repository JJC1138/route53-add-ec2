import argparse
import sys

def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('instance_id', metavar='instance-id', help="The ID of the EC2 instance.")
    arg_parser.add_argument('hostname', help="The hostname that you want to point to the EC2 instance. It must be in a Route 53 zone that you can modify.")
    if len(sys.argv) == 1:
        sys.argv.append('-h')
    args = arg_parser.parse_args()
