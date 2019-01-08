import argparse
import sys

import boto3

def log(message):
    print(message, file=sys.stderr)

def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('instance_id', metavar='instance-id', help="The ID of the EC2 instance.")
    arg_parser.add_argument('hostname', help="The hostname that you want to point to the EC2 instance. It must be in a Route 53 zone that you can modify.")
    if len(sys.argv) == 1:
        sys.argv.append('-h')
    args = arg_parser.parse_args()
    
    r53 = boto3.client('route53')
    
    if not args.hostname.endswith('.'): args.hostname = args.hostname + '.'
    
    log('Looking for Route53 zone for %s' % args.hostname)
    
    zones = r53.list_hosted_zones()
    
    zone_id = None
    
    longest_matching_zone_name_length = -1
    
    for zone in zones['HostedZones']:
        zone_name = zone['Name']
        if args.hostname.endswith(zone_name):
            # It's quite possible that a user might have more than one plausible matching zone, because they might have e.g. example.com and sub.example.com. If we have more than one match then we want to use the most-specific one, which will be the longest one:
            zone_name_length = len(zone_name)
            if zone_name_length > longest_matching_zone_name_length:
                zone_id = zone['Id']
                longest_matching_zone_name_length = zone_name_length
    
    if zone_id is None:
        raise Exception('No Route53 zone found for %s' % args.hostname)
    else:
        log("Found zone ID %s" % zone_id)
    
    log('Getting existing record\'s TTL')
    
    ttl = None
    
    record_sets = r53.list_resource_record_sets(
        HostedZoneId=zone_id, StartRecordName=args.hostname, StartRecordType='A', MaxItems='1'
        )['ResourceRecordSets']
    if len(record_sets) > 0:
        record_set = record_sets[0]
        # Because we're only using StartRecordName to filter, if the record doesn't exist then we might have some other record:
        if record_set['Name'] == args.hostname:
            ttl = record_set['TTL']
    
    if ttl is None:
        ttl = 60
        log("No existing record found. New record will have TTL of %d" % ttl)
    else:
        log("Found existing record with TTL %d" % ttl)
    
    ec2 = boto3.resource('ec2')
    
    log("Fetching EC2 instance information")
    instance = next(iter(ec2.instances.filter(InstanceIds=[args.instance_id])))
    
    ipv4_address = instance.public_ip_address
    log("Found IPv4 address %s" % ipv4_address)
    
    ipv6_address = None
    network_interfaces = getattr(instance, 'network_interfaces', None)
    if network_interfaces is not None and len(network_interfaces) > 0:
        if len(network_interfaces) != 1:
            raise Exception("This tool doesn't support instances with more than one network interface.")
        ipv6_addresses = getattr(network_interfaces[0], 'ipv6_addresses', None)
        if ipv6_addresses is not None and len(ipv6_addresses) > 0:
            if len(ipv6_addresses) != 1:
                raise Exception("This tool doesn't support instances with more than one IPv6 address.")
            ipv6_address = ipv6_addresses[0]['Ipv6Address']
    
    if ipv6_address is None:
        log("No IPv6 address found")
    else:
        log("Found IPv6 address %s" % ipv6_address)
