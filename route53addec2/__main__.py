import argparse
import sys
import time

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
    
    changes = []
    
    for doing_ipv6_change in (False, True):
        record_type = 'AAAA' if doing_ipv6_change else 'A'
        ip = ipv6_address if doing_ipv6_change else ipv4_address
        ip_version_string = 'IPv6' if doing_ipv6_change else 'IPv4'
        
        record_sets = r53.list_resource_record_sets(
            HostedZoneId=zone_id, StartRecordName=args.hostname, StartRecordType=record_type, MaxItems='1'
        )['ResourceRecordSets']
        
        existing_ttl = None
        
        if len(record_sets) > 1:
            # This shouldn't be able to happen as far as I'm aware.
            raise Exception("Multiple record sets returned, and we don't know how to handle that.")
        
        elif len(record_sets) == 1:
            record_set = record_sets[0]
            
            if record_set['Type'] == record_type and (record_set['Name'] == args.hostname or record_set['Name'] == '%s.' % args.hostname):
                records = record_set.get('ResourceRecords', [])
            else:
                # The API has returned some other record set which means there wasn't an exact match for the one we asked for.
                records = []
            
            if len(records) > 1:
                raise Exception("Multiple addresses found on %s record so this record has been modified by someone or something other than this tool. Please delete all but one of the values to use the record with this tool." % record_type)
            
            elif len(records) == 1:
                existing_ttl = record_set['TTL']
                existing_ip = records[0]['Value']
                
                if existing_ip == ip:
                    log("Record is already set to correct %s address %s" % (ip_version_string, ip))
                    continue
                else:
                    log("Found existing %s record with TTL of %d" % (ip_version_string, existing_ttl))
            
            elif len(records) == 0:
                record_sets = []
        
        if len(record_sets) == 0:
            if ip is None:
                log("No %s address record exists and we don't have an address of that type" % ip_version_string)
                continue
        
        if ip:
            ttl = existing_ttl or 60
            log("Setting record to point to %s address %s with TTL %d" % (ip_version_string, ip, ttl))
        else:
            ttl = existing_ttl
            log("Removing record for %s address because we don't have an address of that type" % ip_version_string)
        
        change = {
            'Action': 'UPSERT' if ip is not None else 'DELETE',
            'ResourceRecordSet': {
                'Name': args.hostname,
                'Type': record_type,
                'TTL': ttl,
                'ResourceRecords': [
                    {
                        'Value': ip or existing_ip,
                    }
                ],
            },
        }
        
        changes.append(change)
    
    if len(changes) == 0:
        # All records are correct already.
        return
    
    response = r53.change_resource_record_sets(
        HostedZoneId = zone_id,
        ChangeBatch = { 'Changes': changes })
    
    while response['ChangeInfo']['Status'] != 'INSYNC':
        log("Waiting for DNS update to propagate")
        time.sleep(15)
        response = r53.get_change(Id=response['ChangeInfo']['Id'])
    
    log("DNS has finished propagating")
