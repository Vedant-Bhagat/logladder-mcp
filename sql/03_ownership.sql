-- Fictional ownership (spec 01 §4.4). Components missing here end up as team 'Unowned' in episodes.
INSERT INTO ownership (id, dataset, component, team, team_lead, notes) VALUES
    (1,  'bgl',       'KERNEL',         'HPC Kernel & Runtime',        'Mira Hoffmann', 'fictional'),
    (2,  'bgl',       'APP',            'HPC Applications Support',    'Daniel Ortiz',  'fictional'),
    (3,  'bgl',       'MMCS',           'HPC Control System',          'Lena Brandt',   'fictional'),
    (4,  'bgl',       'BGLMASTER',      'HPC Control System',          'Lena Brandt',   'fictional'),
    (5,  'bgl',       'CMCS',           'HPC Control System',          'Lena Brandt',   'fictional'),
    (6,  'bgl',       'LINKCARD',       'HPC Hardware & Interconnect', 'Sam Okafor',    'fictional'),
    (7,  'bgl',       'HARDWARE',       'HPC Hardware & Interconnect', 'Sam Okafor',    'fictional'),
    (8,  'bgl',       'DISCOVERY',      'HPC Hardware & Interconnect', 'Sam Okafor',    'fictional'),
    (9,  'bgl',       'MONITOR',        'HPC Hardware & Interconnect', 'Sam Okafor',    'fictional'),
    (10, 'openstack', 'nova-api',       'Cloud API Platform',          'Priya Raman',   'fictional'),
    (11, 'openstack', 'nova-scheduler', 'Cloud Scheduling',            'Tom Becker',    'fictional'),
    (12, 'openstack', 'nova-compute',   'Cloud Compute & Hypervisors', 'Aisha Yilmaz',  'fictional');
